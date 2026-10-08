from __future__ import annotations

import json
import threading

from .analysis import measure, propose_phases
from .db import now
from .perception import analyze as extract_tracks
from .provider import assist
from .reports import build_report


class Worker:
    def __init__(self, settings, repo):
        self.settings, self.repo = settings, repo
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True, name="shot-worker")

    def start(self):
        self.repo.recover()
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=5)

    def loop(self):
        while not self.stop.is_set():
            job = self.repo.claim_job()
            if not job:
                self.wake.wait(1)
                self.wake.clear()
                continue
            self.execute(job)

    def cancelled(self, job_id):
        return self.stop.is_set() or self.repo.get("job", job_id)["cancel_requested"]

    def tracks(self, asset):
        return json.loads(self.settings.resolve(asset["tracks_path"]).read_text())

    def render(self, job_id, asset, request):
        reference = (
            self.repo.get("asset", request["reference_asset_id"])
            if request.get("reference_asset_id")
            else None
        )
        if reference and not reference.get("measurements"):
            raise ValueError("reference_unanalyzed")
        if reference and reference["id"] == asset["id"]:
            raise ValueError("self_reference")
        self.repo.patch("job", job_id, stage="rendering")
        report = build_report(
            self.settings,
            asset,
            self.tracks(asset),
            reference,
            self.tracks(reference) if reference else None,
            request.get("locale", "en"),
            request.get("assume_same_view", False),
            lambda: self.cancelled(job_id),
        )
        self.repo.put("report", report)
        if self.cancelled(job_id):
            raise InterruptedError("cancelled")
        self.repo.publish_report(asset["id"], asset["revision"], report, request, reference)
        return report["id"]

    def execute(self, job):
        key = job["id"]
        payload = job["payload"]
        done = []
        errors = []
        try:
            if job["kind"] == "report":
                asset = self.repo.get("asset", payload["asset_id"])
                if asset["revision"] != payload["expected_revision"]:
                    raise ValueError("stale_revision")
                done.append(self.render(key, asset, payload))
            else:
                config = payload["config"]
                for asset_id in payload["asset_ids"]:
                    if self.cancelled(key):
                        raise InterruptedError("cancelled")
                    asset = self.repo.get("asset", asset_id)
                    revision = asset["revision"]
                    try:
                        asset = self.repo.begin_analysis(
                            asset_id, payload.get("asset_revisions", {}).get(asset_id, revision)
                        )
                        revision = asset["revision"]
                        self.repo.patch("job", key, stage="pose_and_ball", current_asset_id=asset_id)
                        track = (
                            self.tracks(asset)
                            if asset.get("tracks_path")
                            else extract_tracks(
                                self.settings,
                                asset,
                                lambda n, total: self.repo.patch(
                                    "job", key, progress={"frames": n, "total_frames": total}
                                ),
                                lambda: self.cancelled(key),
                            )
                        )
                        path = self.settings.resolve(f"assets/{asset_id}/tracks.json")
                        path.write_text(json.dumps(track))
                        phases, side, origin = propose_phases(track, config)
                        if (asset.get("phases", {}).get("release") or {}).get("source") == "user_corrected":
                            phases["release"] = asset["phases"]["release"]
                        local_phases = dict(phases)
                        model = None
                        model_error = None
                        if config["mode"] != "local":
                            try:
                                model = assist(
                                    self.settings,
                                    self.repo,
                                    key,
                                    {**asset, "phases": phases},
                                    config,
                                    lambda: self.cancelled(key),
                                )
                                if (
                                    model["release"]
                                    and (phases.get("release") or {}).get("source") != "user_corrected"
                                ):
                                    phases["release"] = model["release"]
                            except ValueError as exc:
                                model_error = str(exc)
                                errors.append({"asset_id": asset_id, "code": model_error})
                        updated = self.repo.update_if_revision(
                            asset_id,
                            revision,
                            tracks_path=str(path.relative_to(self.settings.data_dir)),
                            phases=phases,
                            measurements=measure(track, phases, side, origin),
                            analysis_config=config,
                            local_phase_proposal=local_phases,
                            model_assist=model,
                            model_error=model_error,
                            analyzed_at=now(),
                        )
                        if not updated:
                            raise ValueError("stale_revision")
                        done.append(self.render(key, updated, {"locale": config["locale"]}))
                    except InterruptedError:
                        self.repo.update_if_revision(asset_id, revision, status="cancelled")
                        raise
                    except Exception as exc:
                        self.repo.update_if_revision(asset_id, revision, status="analysis_failed")
                        code = str(exc) if isinstance(exc, (ValueError, KeyError)) else type(exc).__name__
                        errors.append({"asset_id": asset_id, "code": code})
                    self.repo.patch(
                        "job", key, completed=len(done), total=len(payload["asset_ids"]), errors=errors
                    )
            if self.cancelled(key):
                raise InterruptedError("cancelled")
            self.repo.patch(
                "job",
                key,
                status="partial" if errors and done else ("failed" if errors else "succeeded"),
                stage="complete",
                output_report_ids=done,
                errors=errors,
            )
        except InterruptedError:
            self.repo.patch(
                "job", key, status="cancelled", stage="cancelled", output_report_ids=done, errors=errors
            )
        except Exception as exc:
            code = str(exc) if isinstance(exc, (ValueError, KeyError)) else type(exc).__name__
            self.repo.patch("job", key, status="failed", stage="failed", error_code=code, errors=errors)
