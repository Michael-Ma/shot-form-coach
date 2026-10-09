from __future__ import annotations

import json
import tempfile
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analysis import measure
from .coaching import build_review
from .codex_runner import codex_status
from .config import ROOT, Settings
from .contracts import (
    AssetLabel,
    ClipSpan,
    CreateAnalysis,
    PhaseCorrection,
    ReportRequest,
    RevisionRequest,
    TrimSpan,
)
from .db import Repository
from .lifecycle import asset_lifecycle, create_clip, import_video, sessions, trim_clip
from .media import MediaError, ingest
from .pose_comparison import build_pose_comparison
from .provider import ensure_ready
from .provider_diagnostics import with_model_diagnostic
from .review_data import current_measurements
from .worker import Worker


@lru_cache(maxsize=32)
def load_pose_track(path: str, modified_ns: int):
    return json.loads(Path(path).read_text())


def create_app(settings=None, start_worker=True):
    settings = settings or Settings.from_env()
    settings.prepare()
    repo = Repository(settings.db_path)
    worker = Worker(settings, repo)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        yield
        if start_worker:
            worker.close()

    api = FastAPI(title="Shot Form Coach", lifespan=lifespan)
    api.state.repo = repo
    api.state.worker = worker

    def get(kind, key):
        try:
            return repo.get(kind, key)
        except KeyError:
            raise HTTPException(404, "not_found") from None

    def public(asset):
        asset = current_measurements(settings, asset)
        asset = asset_lifecycle(asset)
        asset = with_model_diagnostic(settings, repo, asset)
        asset["coaching"] = build_review(asset)
        if asset.get("report"):
            asset["report"] = {
                k: v for k, v in asset["report"].items() if k not in ("video_evidence", "image_evidence")
            }
        return {
            **{k: v for k, v in asset.items() if k not in ("preview_path", "original_path", "tracks_path")},
            "preview_url": f"/api/assets/{asset['id']}/preview",
        }

    def queue(kind, payload, idempotency_key=None):
        try:
            with repo.lock:
                for asset_id in payload.get("asset_ids", []):
                    repo.assert_available(
                        repo.get("asset", asset_id), payload.get("asset_revisions", {}).get(asset_id)
                    )
                if payload.get("asset_id"):
                    repo.assert_available(
                        repo.get("asset", payload["asset_id"]), payload.get("expected_revision")
                    )
                if payload.get("reference_asset_id"):
                    repo.assert_available(repo.get("asset", payload["reference_asset_id"]))
                job = repo.new_job(kind, payload, idempotency_key)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        worker.wake.set()
        return job

    def available(key):
        a = get("asset", key)
        try:
            repo.assert_available(a)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return a

    def video_public(video, include_trashed=False, detail=False):
        result = {
            k: v
            for k, v in video.items()
            if k not in ("original_path", "preview_path", "thumbnail_path", "raw_pts_origin", "clips")
        }
        evidence = video.get("scan_evidence")
        if evidence:
            # The UI polls these summaries. Detailed traces are fetched explicitly.
            result["scan_evidence"] = {
                k: v for k, v in evidence.items() if k not in ("decision_trace", "anomaly_events")
            }
            result["scan_diagnostics_url"] = f"/api/videos/{video['id']}/scan-diagnostics"
        result["preview_url"] = f"/api/videos/{video['id']}/preview" if video.get("preview_path") else None
        result["thumbnail_url"] = (
            f"/api/videos/{video['id']}/thumbnail" if video.get("thumbnail_path") else None
        )
        if not result["thumbnail_url"] and video.get("clips"):
            first = next((a for a in video["clips"] if not a.get("trashed_at")), video["clips"][0])
            result["thumbnail_url"] = f"/api/assets/{first['id']}/frames/0"
        if detail:
            result["clips"] = [
                public(a) for a in video.get("clips", []) if include_trashed or not a.get("trashed_at")
            ]
        return result

    def video_session(key):
        value = next((v for v in sessions(repo) if v["id"] == key), None)
        if value is None:
            raise HTTPException(404, "not_found")
        return value

    def queue_video(key, kind):
        with repo.lock:
            video = get("video", key)
            current = next(
                (
                    j
                    for j in repo.all("job")
                    if j["kind"] == kind
                    and j.get("payload", {}).get("video_id") == key
                    and j["status"] in ("queued", "running")
                ),
                None,
            )
            if current:
                return current
            if kind == "video_scan" and video["status"] != "ready":
                raise HTTPException(409, "video_not_ready")
            repo.patch(
                "video",
                key,
                **(
                    {"status": "processing", "error_code": None}
                    if kind == "video_import"
                    else {"scan_status": "queued", "scan_error": None}
                ),
            )
            return queue(kind, {"video_id": key})

    @api.get("/api/videos")
    def videos():
        return [video_public(v) for v in sessions(repo)]

    @api.post("/api/videos/upload")
    def upload_video(file: UploadFile):
        try:
            video = import_video(settings, repo, file.file, Path(file.filename or "Practice video").name)
        except MediaError as exc:
            raise HTTPException(413 if str(exc) == "upload_too_large" else 422, str(exc)) from None
        except Exception:
            raise HTTPException(422, "invalid_video") from None
        job = queue_video(video["id"], "video_import") if video["status"] != "ready" else None
        return {"video": video_public(video_session(video["id"]), detail=True), "job": job}

    @api.get("/api/videos/{key}")
    def video(key: str, include_trashed: bool = False):
        return video_public(video_session(key), include_trashed=include_trashed, detail=True)

    @api.get("/api/videos/{key}/scan-diagnostics")
    def scan_diagnostics(key: str):
        video = get("video", key)
        if not video.get("scan_evidence"):
            raise HTTPException(404, "scan_diagnostics_unavailable")
        return {
            "video_id": key,
            "scan_status": video.get("scan_status"),
            "scan_error": video.get("scan_error"),
            "last_successful_scan_evidence": video["scan_evidence"],
        }

    @api.get("/api/videos/{key}/preview")
    def video_preview(key: str):
        video = get("video", key)
        if not video.get("preview_path"):
            raise HTTPException(409, "video_not_ready")
        return FileResponse(settings.resolve(video["preview_path"]), media_type="video/mp4")

    @api.get("/api/videos/{key}/thumbnail")
    def video_thumbnail(key: str):
        video = get("video", key)
        if not video.get("thumbnail_path"):
            raise HTTPException(404, "thumbnail_not_ready")
        return FileResponse(settings.resolve(video["thumbnail_path"]), media_type="image/jpeg")

    @api.post("/api/videos/{key}/prepare")
    def retry_prepare(key: str):
        return queue_video(key, "video_import")

    @api.post("/api/videos/{key}/scan")
    def scan(key: str):
        return queue_video(key, "video_scan")

    @api.post("/api/videos/{key}/clips")
    def add_clip(key: str, request: ClipSpan):
        get("video", key)
        try:
            return public(create_clip(settings, repo, key, request))
        except MediaError as exc:
            raise HTTPException(422, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @api.post("/api/videos/{key}/candidates/{candidate_id}/dismiss")
    def dismiss_candidate(key: str, candidate_id: str):
        with repo.lock:
            video = get("video", key)
            candidate = next((c for c in video.get("candidates", []) if c["id"] == candidate_id), None)
            if not candidate:
                raise HTTPException(404, "candidate_not_found")
            if candidate["status"] != "proposed":
                raise HTTPException(409, "candidate_not_proposed")
            candidate["status"] = "dismissed"
            repo.patch("video", key, candidates=video["candidates"])
        return video_public(video_session(key), detail=True)

    @api.get("/api/health")
    def health():
        return {
            "status": "ok",
            "app": "shot-form-coach",
            "version": "0.6.2",
            "gemini_configured": bool(settings.api_key),
            "gemini_model": settings.model_id,
            "astra_model": settings.astra_model,
            "astra_api_configured": bool(settings.openai_api_key),
            "codex": {k: v for k, v in codex_status(settings.codex_bin).items() if k != "binary"},
            "models_ready": all(
                (settings.data_dir / "models" / p).is_file()
                for p in ["pose_landmarker_full.task", "yolox_s.onnx"]
            ),
        }

    @api.get("/api/assets")
    def assets(include_trashed: bool = False):
        return [public(a) for a in repo.all("asset") if include_trashed or not a.get("trashed_at")]

    @api.patch("/api/assets/{key}")
    def rename_asset(key: str, request: AssetLabel):
        get("asset", key)
        try:
            return public(
                repo.change_asset(
                    key,
                    request.expected_revision,
                    "label",
                    request.label,
                    request.expected_lifecycle_revision,
                )
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @api.post("/api/assets/{key}/trash")
    def trash_asset(key: str, request: RevisionRequest):
        get("asset", key)
        try:
            return public(
                repo.change_asset(
                    key,
                    request.expected_revision,
                    "trash",
                    expected_lifecycle_revision=request.expected_lifecycle_revision,
                )
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @api.post("/api/assets/{key}/restore")
    def restore_asset(key: str, request: RevisionRequest):
        get("asset", key)
        try:
            return public(
                repo.change_asset(
                    key,
                    request.expected_revision,
                    "restore",
                    expected_lifecycle_revision=request.expected_lifecycle_revision,
                )
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @api.put("/api/assets/{key}/trim")
    def trim_asset(key: str, request: TrimSpan):
        get("asset", key)
        try:
            return public(trim_clip(settings, repo, key, request))
        except MediaError as exc:
            raise HTTPException(422, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @api.get("/api/assets/{key}")
    def asset(key: str):
        return public(get("asset", key))

    @api.get("/api/assets/{key}/preview")
    def preview(key: str):
        return FileResponse(settings.resolve(get("asset", key)["preview_path"]), media_type="video/mp4")

    @api.get("/api/assets/{key}/frames/{index}")
    def frame(key: str, index: int):
        a = get("asset", key)
        if not 0 <= index < len(a["frame_index"]):
            raise HTTPException(404, "frame_not_found")
        return FileResponse(settings.resolve(a["frame_index"][index]["path"]), media_type="image/jpeg")

    @api.get("/api/assets/{key}/tracks")
    def tracks(key: str):
        a = get("asset", key)
        if not a.get("tracks_path"):
            raise HTTPException(404, "not_analyzed")
        return json.loads(settings.resolve(a["tracks_path"]).read_text())

    @api.get("/api/assets/{key}/pose-comparison")
    def pose_comparison(
        key: str,
        mode: Literal["teaching", "reference"] = "teaching",
        reference_asset_id: str | None = None,
        assume_same_view: bool = False,
    ):
        a = current_measurements(settings, available(key))
        ref = current_measurements(settings, available(reference_asset_id)) if reference_asset_id else None

        def track(asset):
            if not asset or not asset.get("tracks_path"):
                return None
            path = settings.resolve(asset["tracks_path"])
            try:
                return load_pose_track(str(path), path.stat().st_mtime_ns)
            except (OSError, ValueError):
                return None

        result = build_pose_comparison(a, track(a), ref, track(ref), mode, assume_same_view)
        result["reference_asset_id"] = ref["id"] if ref else None
        result["reference_revision"] = ref["revision"] if ref else None
        return result

    @api.post("/api/assets/upload")
    def upload(file: UploadFile):
        total = 0
        with tempfile.NamedTemporaryFile() as temp:
            while data := file.file.read(1024 * 1024):
                total += len(data)
                if total > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "upload_too_large")
                temp.write(data)
            temp.flush()
            if not total:
                raise HTTPException(422, "empty_upload")
            try:
                return public(ingest(settings, repo, Path(temp.name), Path(file.filename or "Shot").name))
            except MediaError:
                raise HTTPException(422, "invalid_or_long_video") from None

    @api.post("/api/analyses")
    def analyze(request: CreateAnalysis, idempotency_key: str | None = Header(default=None)):
        for key in request.asset_ids:
            available(key)
        if len(set(request.asset_ids)) != len(request.asset_ids):
            raise HTTPException(422, "duplicate_assets")
        if request.config.allow_unknown_retry and len(request.asset_ids) != 1:
            raise HTTPException(422, "retry_ack_single_shot_only")
        if request.config.mode != "local" and not request.config.allow_unknown_retry:
            provider = {"gemini": "gemini", "astra_api": "openai", "astra_codex": "codex"}[
                request.config.mode
            ]
            if any(
                receipt.get("asset_id") in request.asset_ids
                and receipt.get("provider", "gemini") == provider
                and receipt.get("status") in ("submitting", "request_unknown")
                for previous in repo.all("job")
                for receipt in previous.get("receipts", [])
            ):
                raise HTTPException(409, "unresolved_request_blocks_resubmission")
        try:
            ensure_ready(settings, request.config.mode)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if request.config.mode != "local" and len(request.asset_ids) > request.config.max_model_calls:
            raise HTTPException(422, "model_call_budget_exhausted")
        return queue(
            "analysis",
            {
                **request.model_dump(),
                "asset_revisions": {key: get("asset", key)["revision"] for key in request.asset_ids},
            },
            idempotency_key,
        )

    @api.get("/api/jobs")
    def jobs():
        return repo.all("job")

    @api.get("/api/jobs/{key}")
    def job(key: str):
        return get("job", key)

    @api.post("/api/jobs/{key}/cancel")
    def cancel(key: str):
        with repo.lock:
            j = get("job", key)
            if j["status"] in ("queued", "running"):
                if j["status"] == "queued" and j["kind"] in ("video_import", "video_scan"):
                    worker.video_failure(j, "cancelled")
                return repo.patch(
                    "job",
                    key,
                    cancel_requested=True,
                    **({"status": "cancelled", "stage": "cancelled"} if j["status"] == "queued" else {}),
                )
            return j

    @api.put("/api/assets/{key}/phases")
    def correct(key: str, request: PhaseCorrection):
        a = available(key)
        if not a.get("tracks_path"):
            raise HTTPException(422, "not_analyzed")
        try:
            a = repo.correct_phase(key, request)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        track = json.loads(settings.resolve(a["tracks_path"]).read_text())
        old = a["measurements"]
        repo.update_if_revision(
            key, a["revision"], measurements=measure(track, a["phases"], old["side"], old["side_source"])
        )
        previous = a.get("report_request", {})
        job = queue(
            "report",
            {
                **previous,
                "asset_id": key,
                "expected_revision": a["revision"],
                "locale": request.locale or previous.get("locale", "en"),
            },
        )
        return {"asset": public(repo.get("asset", key)), "job": job}

    @api.post("/api/assets/{key}/reports")
    def report(key: str, request: ReportRequest):
        a = available(key)
        if not a.get("measurements"):
            raise HTTPException(422, "not_analyzed")
        if a["revision"] != request.expected_revision:
            raise HTTPException(409, "stale_revision")
        if request.reference_asset_id:
            ref = available(request.reference_asset_id)
            if ref["id"] == key or not ref.get("measurements"):
                raise HTTPException(422, "invalid_reference")
        return queue("report", {"asset_id": key, **request.model_dump()})

    @api.get("/api/reports/{key}/{kind}")
    def artifact(key: str, kind: str):
        r = get("report", key)
        if kind not in r["artifacts"]:
            raise HTTPException(404, "artifact_not_found")
        return FileResponse(
            settings.resolve(r["artifacts"][kind]),
            filename=f"shot-review-{r['asset_id']}-r{r['asset_revision']}"
            + {"image": ".jpg", "video": ".mp4", "text": ".md", "json": ".json"}[kind],
        )

    @api.get("/api/sources")
    def sources():
        return json.loads((ROOT / "references/sources.json").read_text())

    if (ROOT / "web/dist").is_dir():
        api.mount("/", StaticFiles(directory=ROOT / "web/dist", html=True), name="web")
    return api


app = create_app()
