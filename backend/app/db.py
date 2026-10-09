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

    def put_many(self, records):
        """Publish related lifecycle changes atomically."""
        with self.lock, self.connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO records VALUES(?,?,?)",
                [(kind, value["id"], json.dumps(value, ensure_ascii=False)) for kind, value in records],
            )

    def assert_available(self, asset, expected_revision=None, allow_trashed=False):
        if expected_revision is not None and asset.get("revision", 0) != expected_revision:
            raise ValueError("stale_revision")
        if asset.get("trashed_at") and not allow_trashed:
            raise ValueError("asset_trashed")

    def assert_idle(self, asset_id):
        for job in self.all("job"):
            if job["status"] not in ("queued", "running"):
                continue
            payload = job.get("payload", {})
            if asset_id in payload.get("asset_ids", []) or asset_id in (
                payload.get("asset_id"),
                payload.get("reference_asset_id"),
            ):
                raise ValueError("asset_busy")

    def change_asset(self, asset_id, expected_revision, operation, label=None, expected_lifecycle_revision=0):
        with self.lock:
            asset = self.get("asset", asset_id)
            self.assert_available(asset, expected_revision, allow_trashed=operation == "restore")
            if asset.get("lifecycle_revision", 0) != expected_lifecycle_revision:
                raise ValueError("stale_lifecycle_revision")
            self.assert_idle(asset_id)
            if operation == "label":
                if not label or not label.strip():
                    raise ValueError("invalid_label")
                asset["label"] = label.strip()
                asset.update(report=None, report_invalid_reason="label_changed")
            elif operation == "trash":
                asset["trashed_at"] = now()
            elif operation == "restore":
                if not asset.get("trashed_at"):
                    raise ValueError("asset_not_trashed")
                asset["trashed_at"] = None
            else:
                raise ValueError("invalid_operation")
            # Metadata uses a separate token; unchanged pixels/phases retain paid coaching.
            asset.update(lifecycle_revision=asset.get("lifecycle_revision", 0) + 1, updated_at=now())
            if operation in ("label", "trash"):
                self.invalidate_dependents(asset_id)
            return self.put("asset", asset)

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
            self.assert_available(asset)
            self.assert_idle(asset_id)
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

    def begin_analysis(self, asset_id, expected_revision, job_id=None):
        with self.lock:
            asset = self.get("asset", asset_id)
            self.assert_available(asset)
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
            if job_id:
                asset["active_job_id"] = job_id
            self.invalidate_dependents(asset_id)
            return self.put("asset", asset)

    def publish_report(self, asset_id, revision, report, request, reference):
        with self.lock:
            self.assert_available(self.get("asset", asset_id))
            if reference:
                current_reference = self.get("asset", reference["id"])
                self.assert_available(current_reference)
                if current_reference["revision"] != reference["revision"]:
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
            if job["kind"] == "analysis":
                for asset_id in job.get("payload", {}).get("asset_ids", []):
                    try:
                        asset = self.get("asset", asset_id)
                    except KeyError:
                        continue
                    owned = asset.get("active_job_id") == job["id"] or (
                        not asset.get("active_job_id") and job.get("current_asset_id") == asset_id
                    )
                    if asset.get("status") != "analyzing" or not owned:
                        continue
                    current_unknown = any(
                        r.get("asset_id") == asset_id
                        and r.get("asset_revision") == asset.get("revision")
                        and r.get("status") == "request_unknown"
                        for r in receipts
                    )
                    self.patch(
                        "asset",
                        asset_id,
                        status="analysis_failed",
                        active_job_id=None,
                        analysis_error="worker_interrupted",
                        model_error="request_unknown" if current_unknown else "worker_interrupted",
                    )
            video_id = job.get("payload", {}).get("video_id")
            if video_id and job["kind"] in ("video_import", "video_scan"):
                self.patch(
                    "video",
                    video_id,
                    **(
                        {"status": "failed", "error_code": "worker_interrupted"}
                        if job["kind"] == "video_import"
                        else {"scan_status": "failed", "scan_error": "worker_interrupted"}
                    ),
                )
