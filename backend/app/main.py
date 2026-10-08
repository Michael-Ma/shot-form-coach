from __future__ import annotations

import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analysis import measure
from .config import ROOT, Settings
from .contracts import CreateAnalysis, ImportWorkbench, PhaseCorrection, ReportRequest
from .db import Repository
from .media import MediaError, import_workbench, ingest
from .worker import Worker


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
        return {
            **{k: v for k, v in asset.items() if k not in ("preview_path", "original_path", "tracks_path")},
            "preview_url": f"/api/assets/{asset['id']}/preview",
        }

    def queue(kind, payload, idempotency_key=None):
        try:
            job = repo.new_job(kind, payload, idempotency_key)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        worker.wake.set()
        return job

    @api.get("/api/health")
    def health():
        return {
            "status": "ok",
            "app": "shot-form-coach",
            "version": "0.2.0",
            "gemini_configured": bool(settings.api_key),
            "gemini_model": settings.model_id,
            "models_ready": all(
                (settings.data_dir / "models" / p).is_file()
                for p in ["pose_landmarker_full.task", "yolox_s.onnx"]
            ),
            "workbench_configured": bool(settings.workbench_data),
        }

    @api.get("/api/assets")
    def assets():
        return [public(a) for a in repo.all("asset")]

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

    @api.get("/api/workbench/runs")
    def runs():
        if not settings.workbench_data:
            return []
        result = []
        for folder in (settings.workbench_data / "runs").glob("run_*"):
            path = folder / "results.json"
            if path.is_file():
                try:
                    raw = json.loads(path.read_text())
                    count = sum(
                        e.get("clip_status") == "succeeded" and not e.get("duplicate_of")
                        for e in raw.get("events", [])
                    )
                    if count:
                        result.append({"id": folder.name, "clip_count": count})
                except (ValueError, OSError):
                    continue
        return result

    @api.post("/api/workbench/import")
    def import_run(request: ImportWorkbench):
        try:
            return [public(a) for a in import_workbench(settings, repo, request.run_id)]
        except (MediaError, OSError, KeyError, ValueError):
            raise HTTPException(422, "workbench_import_failed") from None

    @api.post("/api/analyses")
    def analyze(request: CreateAnalysis, idempotency_key: str | None = Header(default=None)):
        for key in request.asset_ids:
            get("asset", key)
        if len(set(request.asset_ids)) != len(request.asset_ids):
            raise HTTPException(422, "duplicate_assets")
        if request.config.mode == "gemini" and not settings.api_key:
            raise HTTPException(422, "api_key_missing")
        if request.config.mode == "gemini" and len(request.asset_ids) > request.config.max_model_calls:
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
        j = get("job", key)
        if j["status"] in ("queued", "running"):
            return repo.patch(
                "job",
                key,
                cancel_requested=True,
                **({"status": "cancelled", "stage": "cancelled"} if j["status"] == "queued" else {}),
            )
        return j

    @api.put("/api/assets/{key}/phases")
    def correct(key: str, request: PhaseCorrection):
        a = get("asset", key)
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
        a = get("asset", key)
        if not a.get("measurements"):
            raise HTTPException(422, "not_analyzed")
        if a["revision"] != request.expected_revision:
            raise HTTPException(409, "stale_revision")
        if request.reference_asset_id:
            ref = get("asset", request.reference_asset_id)
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
