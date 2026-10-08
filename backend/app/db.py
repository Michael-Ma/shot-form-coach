from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat()


def ident(prefix):
    return prefix + "_" + uuid.uuid4().hex


class Repository:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, body TEXT NOT NULL,
                PRIMARY KEY(kind,id));
              CREATE TABLE IF NOT EXISTS idempotency(key TEXT PRIMARY KEY, signature TEXT, job_id TEXT);
            """)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, kind, key):
        with self.connect() as conn:
            row = conn.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        if not row:
            raise KeyError(key)
        return json.loads(row["body"])

    def all(self, kind):
        with self.connect() as conn:
            rows = conn.execute("SELECT body FROM records WHERE kind=?", (kind,)).fetchall()
        return sorted(
            [json.loads(r["body"]) for r in rows], key=lambda r: r.get("created_at", ""), reverse=True
        )

    def put(self, kind, value):
        with self.lock, self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO records VALUES(?,?,?)",
                (kind, value["id"], json.dumps(value, ensure_ascii=False)),
            )
        return value

    def patch(self, kind, key, **changes):
        with self.lock:
            record = self.get(kind, key)
            record.update(changes, updated_at=now())
            return self.put(kind, record)

    def update_if_revision(self, asset_id, revision, **changes):
        with self.lock:
            asset = self.get("asset", asset_id)
            if asset.get("revision", 0) != revision:
                return None
            asset.update(changes, updated_at=now())
            return self.put("asset", asset)

    def correct_phase(self, asset_id, correction):
        with self.lock:
            asset = self.get("asset", asset_id)
            if asset.get("revision", 0) != correction.expected_revision:
                raise ValueError("stale_revision")
            frames = asset.get("frame_index") or []
            if correction.first_clear_frame >= len(frames):
                raise ValueError("invalid_frame")
            a, b = correction.last_contact_frame, correction.first_clear_frame
            lo, hi = frames[a]["time_us"], frames[b]["time_us"]
            if a == b:
                lo = frames[max(0, a - 1)]["time_us"]
                hi = frames[min(len(frames) - 1, b + 1)]["time_us"]
            phases = dict(asset.get("phases") or {})
            previous = dict(phases)
            phases["release"] = {
                "range_us": [lo, hi],
                "frame_range": [a, b],
                "source": "user_corrected",
                "quality": "reviewed_interval",
            }
            revision = asset.get("revision", 0) + 1
            history = asset.get("phase_history", []) + [
                {
                    "revision": revision,
                    "created_at": now(),
                    "actor": "user",
                    "previous_phases": previous,
                    "phases": phases,
                }
            ]
            asset.update(
                revision=revision, phases=phases, phase_history=history, report=None, updated_at=now()
            )
            self.invalidate_dependents(asset_id)
            return self.put("asset", asset)

    def invalidate_dependents(self, asset_id):
        for other in self.all("asset"):
            report = other.get("report")
            if report and report.get("reference_id") == asset_id:
                self.patch("asset", other["id"], report=None, report_invalid_reason="reference_changed")

    def begin_analysis(self, asset_id, expected_revision):
        with self.lock:
            asset = self.get("asset", asset_id)
            if asset["revision"] != expected_revision:
                raise ValueError("stale_revision")
            if asset.get("measurements"):
                asset["revision"] += 1
                asset["phase_history"] = asset.get("phase_history", []) + [
                    {
                        "revision": asset["revision"],
                        "actor": "analysis_rerun",
                        "created_at": now(),
                        "previous_phases": asset["phases"],
                    }
                ]
            asset.update(report=None, status="analyzing")
            self.invalidate_dependents(asset_id)
            return self.put("asset", asset)

    def publish_report(self, asset_id, revision, report, request, reference):
        with self.lock:
            if reference and self.get("asset", reference["id"])["revision"] != reference["revision"]:
                raise ValueError("stale_reference_revision")
            updated = self.update_if_revision(
                asset_id, revision, report=report, status="analyzed", report_request=request
            )
            if not updated:
                raise ValueError("stale_revision")
            return updated

    def new_job(self, kind, payload, idempotency_key=None):
        signature = json.dumps(
            {"kind": kind, "payload": {k: v for k, v in payload.items() if k != "asset_revisions"}},
            sort_keys=True,
        )
        with self.lock:
            if idempotency_key:
                with self.connect() as conn:
                    row = conn.execute("SELECT * FROM idempotency WHERE key=?", (idempotency_key,)).fetchone()
                if row:
                    if row["signature"] != signature:
                        raise ValueError("idempotency_conflict")
                    return self.get("job", row["job_id"])
            job = {
                "id": ident("job"),
                "kind": kind,
                "payload": payload,
                "status": "queued",
                "stage": "queued",
                "progress": {},
                "created_at": now(),
                "updated_at": now(),
                "cancel_requested": False,
                "receipts": [],
                "errors": [],
            }
            self.put("job", job)
            if idempotency_key:
                with self.connect() as conn:
                    conn.execute(
                        "INSERT INTO idempotency VALUES(?,?,?)", (idempotency_key, signature, job["id"])
                    )
            return job

    def claim_job(self):
        with self.lock:
            jobs = sorted(self.all("job"), key=lambda j: j["created_at"])
            for job in jobs:
                if job["status"] == "queued" and not job["cancel_requested"]:
                    return self.patch("job", job["id"], status="running", stage="starting", started_at=now())
        return None

    def recover(self):
        for job in self.all("job"):
            if job["status"] != "running":
                continue
            unknown = any(r.get("status") == "submitting" for r in job.get("receipts", []))
            receipts = [
                {**r, "status": "request_unknown", "cost": {"status": "unknown", "estimated_usd": None}}
                if r.get("status") == "submitting"
                else r
                for r in job.get("receipts", [])
            ]
            self.patch(
                "job",
                job["id"],
                status="partial" if unknown else "failed",
                stage="interrupted",
                receipts=receipts,
                error_code="interrupted_request_unknown" if unknown else "worker_interrupted",
            )
