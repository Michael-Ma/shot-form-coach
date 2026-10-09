import io
import subprocess

import pytest
from app.config import Settings
from app.contracts import ClipSpan, TrimSpan
from app.db import Repository
from app.lifecycle import create_clip, import_video, sessions, trim_clip
from app.main import create_app
from app.media import MediaError, probe
from app.segmentation import propose_candidates
from app.worker import Worker
from fastapi.testclient import TestClient


def make_video(path, duration=35, vfr=False):
    args = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=96x96:rate={20 if vfr else 5}:duration={0.2 if vfr else duration}",
    ]
    if vfr:
        args += ["-vf", "setpts='5/TB+if(eq(N,0),0,if(eq(N,1),0.1/TB,if(eq(N,2),0.25/TB,0.5/TB)))'"]
    args += [
        "-fps_mode",
        "passthrough",
        "-enc_time_base",
        "1:1000000",
        "-video_track_timescale",
        "1000000",
        "-c:v",
        "libx264",
        str(path),
    ]
    subprocess.run(args, check=True)
    return path


@pytest.fixture
def state(tmp_path):
    settings = Settings(tmp_path / "data")
    settings.prepare()
    return settings, Repository(settings.db_path)


def fixture_asset(key="a", run=None):
    return {
        "id": key,
        "revision": 0,
        "label": "Shot 1",
        "created_at": key,
        "duration_us": 1_000_000,
        "frame_index": [],
        "phases": {},
        "report": None,
        "upstream": {"run_id": run, "source_start_us": 3_000_000, "source_end_us": 4_000_000} if run else {},
    }


def test_full_video_upload_prepare_create_trim_trash_restore(state, tmp_path):
    settings, repo = state
    source = make_video(tmp_path / "practice.mp4")
    app = create_app(settings, start_worker=False)
    with TestClient(app) as client:
        with source.open("rb") as file:
            response = client.post("/api/videos/upload", files={"file": ("practice.mp4", file, "video/mp4")})
        assert response.status_code == 200, response.text
        video, job = response.json()["video"], response.json()["job"]
        assert video["duration_us"] == 35_000_000 and video["status"] == "processing"
        assert video["clip_count"] == 0
        assert client.get(f"/api/videos/{video['id']}/preview").status_code == 409
        app.state.worker.execute(job)
        video = client.get(f"/api/videos/{video['id']}").json()
        assert video["status"] == "ready" and video["preview_url"]
        assert client.get(video["preview_url"], headers={"range": "bytes=0-127"}).status_code == 206
        assert (
            client.post(
                f"/api/videos/{video['id']}/clips", json={"start_us": 0, "end_us": 31_000_000}
            ).status_code
            == 422
        )
        response = client.post(
            f"/api/videos/{video['id']}/clips",
            json={"start_us": 1_000_000, "end_us": 3_000_000, "label": "First try"},
        )
        assert response.status_code == 200, response.text
        shot = response.json()
        assert shot["source_start_us"] == 1_000_000 and shot["source_end_us"] == 3_000_000
        assert shot["session_id"] == video["id"]
        original = settings.resolve(repo.get("video", video["id"])["original_path"])
        assert original.read_bytes() == source.read_bytes()
        response = client.put(
            f"/api/assets/{shot['id']}/trim",
            json={"start_us": 1_400_000, "end_us": 2_600_000, "expected_revision": 0},
        )
        assert response.status_code == 200, response.text
        trimmed = response.json()
        assert trimmed["id"] != shot["id"] and trimmed["supersedes"] == shot["id"]
        assert trimmed["source_start_us"] == 1_400_000
        assert not trimmed.get("measurements") and trimmed["report"] is None
        assert len(client.get("/api/assets").json()) == 1
        assert len(client.get("/api/assets?include_trashed=true").json()) == 2
        old = client.get(f"/api/assets/{shot['id']}").json()
        assert old["superseded_by"] == trimmed["id"] and old["trashed_at"]
        assert client.post("/api/analyses", json={"asset_ids": [old["id"]]}).status_code == 409
        assert (
            client.post(f"/api/assets/{old['id']}/restore", json={"expected_revision": 0}).status_code == 409
        )
        assert (
            client.post(
                f"/api/assets/{old['id']}/restore",
                json={
                    "expected_revision": old["revision"],
                    "expected_lifecycle_revision": old["lifecycle_revision"],
                },
            ).status_code
            == 200
        )
        assert len(client.get("/api/assets").json()) == 2
        assert original.is_file()
        with source.open("rb") as file:
            duplicate = client.post("/api/videos/upload", files={"file": ("again.mp4", file)})
        assert duplicate.json()["video"]["id"] == video["id"]
        assert duplicate.json()["job"] is None
        assert len(list((settings.data_dir / "videos").iterdir())) == 1


def test_vfr_nonzero_pts_source_mapping_survives_retrim(state, tmp_path):
    settings, repo = state
    source = make_video(tmp_path / "vfr.mp4", vfr=True)
    with source.open("rb") as file:
        video = import_video(settings, repo, file, source.name)
    assert video["raw_pts_origin_us"] == 5_000_000
    shot = create_clip(settings, repo, video["id"], ClipSpan(start_us=50_000, end_us=510_000))
    assert [f["source_time_us"] for f in shot["frame_index"]] == [100_000, 250_000, 500_000]
    assert probe(settings.resolve(shot["preview_path"]))[1] == [0, 150_000, 400_000]
    trimmed = trim_clip(
        settings, repo, shot["id"], TrimSpan(start_us=240_000, end_us=510_000, expected_revision=0)
    )
    assert [f["source_time_us"] for f in trimmed["frame_index"]] == [250_000, 500_000]
    assert settings.resolve(repo.get("asset", shot["id"])["original_path"]).is_file()


def test_session_groups_workbench_runs_and_legacy_without_relabelling(state):
    _, repo = state
    for key, run in [("a", "run_one"), ("b", "run_one"), ("c", "run_two"), ("d", None), ("e", None)]:
        repo.put("asset", fixture_asset(key, run))
    repo.patch("asset", "b", trashed_at="removed")
    groups = {s["id"]: s for s in sessions(repo)}
    assert len(groups) == 3
    assert groups["workbench_run_one"]["clip_count"] == 1
    assert groups["workbench_run_one"]["trashed_count"] == 1
    assert groups["legacy_standalone"]["clip_count"] == 2
    assert all(a["label"] == "Shot 1" for a in repo.all("asset"))


def test_mutation_stale_active_reference_and_invalidation(state):
    _, repo = state
    a, b = fixture_asset(), fixture_asset("b")
    b["report"] = {"reference_id": "a"}
    repo.put("asset", a)
    repo.put("asset", b)
    queued = repo.new_job("report", {"asset_id": "b", "reference_asset_id": "a"})
    with pytest.raises(ValueError, match="asset_busy"):
        repo.change_asset("a", 0, "trash")
    repo.patch("job", queued["id"], status="cancelled")
    removed = repo.change_asset("a", 0, "trash")
    assert repo.get("asset", "b")["report"] is None
    with pytest.raises(ValueError, match="asset_trashed"):
        repo.begin_analysis("a", removed["revision"])
    with pytest.raises(ValueError, match="stale_lifecycle_revision"):
        repo.change_asset("a", 0, "restore")
    restored = repo.change_asset(
        "a", removed["revision"], "restore", expected_lifecycle_revision=removed["lifecycle_revision"]
    )
    assert not restored["trashed_at"] and restored["revision"] == 0 and restored["lifecycle_revision"] == 2


def test_import_limits_empty_upload_and_invalid_media_leave_no_original(state):
    settings, repo = state
    for data, error in [(b"", "empty_upload"), (b"not a video", None)]:
        with pytest.raises(Exception):
            import_video(settings, repo, io.BytesIO(data), "bad")
    settings.max_video_upload_mb = 0
    with pytest.raises(MediaError, match="upload_too_large"):
        import_video(settings, repo, io.BytesIO(b"x"), "too large")
    assert list((settings.data_dir / "videos").iterdir()) == []
    assert repo.all("video") == []


def test_local_proposals_require_single_person_rise_not_static_raised_arm():
    samples = [
        {"time_us": i * 200_000, "people_detected": 1, "left": v, "right": None}
        for i, v in enumerate([-0.5, -0.2, 0.4, 0.8, 0.9, -0.1])
    ]
    candidates = propose_candidates(samples, 5_000_000)
    assert len(candidates) == 1 and candidates[0]["status"] == "proposed"
    assert candidates[0]["peak_us"] == 800_000
    assert candidates[0]["evidence"]["shot_verified"] is False
    assert candidates[0]["evidence"]["all_shots_found"] is False
    assert propose_candidates([{**s, "people_detected": 2} for s in samples], 5_000_000) == []
    assert propose_candidates([{**s, "left": 1.0} for s in samples], 5_000_000) == []


def test_scan_failure_and_restart_keep_manual_work_available(state, tmp_path):
    settings, repo = state
    source = make_video(tmp_path / "short.mp4", duration=1)
    with source.open("rb") as file:
        video = import_video(settings, repo, file, source.name)
    repo.patch("video", video["id"], status="ready")
    job = repo.new_job("video_scan", {"video_id": video["id"]})
    Worker(settings, repo).execute(job)
    assert repo.get("job", job["id"])["error_code"] == "pose_model_missing"
    assert repo.get("video", video["id"])["status"] == "ready"
    assert repo.get("video", video["id"])["scan_status"] == "failed"
    assert create_clip(settings, repo, video["id"], ClipSpan(start_us=0, end_us=600_000))["id"]
    pending = repo.new_job("video_import", {"video_id": video["id"]})
    repo.patch("job", pending["id"], status="running")
    repo.recover()
    assert repo.get("video", video["id"])["status"] == "failed"
    assert settings.resolve(video["original_path"]).is_file()


def test_metadata_mutations_preserve_paid_coaching_and_reject_stale_forms(state):
    _, repo = state
    a = {
        **fixture_asset(),
        "model_assist": {"asset_revision": 0, "coaching": {"sentinel": "paid"}},
        "report": {"id": "existing_export", "asset_revision": 0},
    }
    repo.put("asset", a)
    renamed = repo.change_asset("a", 0, "label", "Renamed")
    assert renamed["revision"] == 0 and renamed["lifecycle_revision"] == 1
    assert renamed["model_assist"] == a["model_assist"] and renamed["report"] is None
    with pytest.raises(ValueError, match="stale_lifecycle_revision"):
        repo.change_asset("a", 0, "label", "Stale form")
    removed = repo.change_asset("a", 0, "trash", expected_lifecycle_revision=1)
    restored = repo.change_asset("a", 0, "restore", expected_lifecycle_revision=2)
    assert removed["model_assist"] == restored["model_assist"] == a["model_assist"]
    assert restored["revision"] == 0 and restored["report"] is None


def test_recreating_trashed_range_makes_new_active_clip(state, tmp_path):
    settings, repo = state
    source = make_video(tmp_path / "short.mp4", duration=1)
    with source.open("rb") as file:
        video = import_video(settings, repo, file, source.name)
    request = ClipSpan(start_us=0, end_us=800_000)
    old = create_clip(settings, repo, video["id"], request)
    repo.change_asset(old["id"], 0, "trash")
    new = create_clip(settings, repo, video["id"], request)
    assert new["id"] != old["id"] and not new.get("trashed_at")
    assert repo.get("asset", old["id"])["trashed_at"]


def test_cancel_queued_source_jobs_is_recoverable(state, tmp_path):
    settings, repo = state
    source = make_video(tmp_path / "short.mp4", duration=1)
    with source.open("rb") as file:
        video = import_video(settings, repo, file, source.name)
    with TestClient(create_app(settings, start_worker=False)) as client:
        job = client.post(f"/api/videos/{video['id']}/prepare").json()
        assert client.post(f"/api/jobs/{job['id']}/cancel").json()["status"] == "cancelled"
        assert repo.get("video", video["id"])["status"] == "failed"
        next_job = client.post(f"/api/videos/{video['id']}/prepare").json()
        assert next_job["id"] != job["id"]
        assert repo.get("video", video["id"])["status"] == "processing"
        repo.patch("job", next_job["id"], status="cancelled")
        repo.patch("video", video["id"], status="ready")
        scan = client.post(f"/api/videos/{video['id']}/scan").json()
        client.post(f"/api/jobs/{scan['id']}/cancel")
        assert repo.get("video", video["id"])["scan_status"] == "failed"
        assert client.post(f"/api/videos/{video['id']}/scan").json()["id"] != scan["id"]


def test_recover_analysis_updates_only_interrupted_asset_and_preserves_unknown_receipt(state):
    _, repo = state
    a, b = fixture_asset(), fixture_asset("b")
    a.update(status="analyzed", report={"id": "completed_report"})
    repo.put("asset", a)
    repo.put("asset", b)
    job = repo.new_job("analysis", {"asset_ids": ["a", "b"]})
    repo.begin_analysis("b", 0, job_id=job["id"])
    repo.patch(
        "job",
        job["id"],
        status="running",
        current_asset_id="b",
        receipts=[{"asset_id": "b", "asset_revision": 0, "status": "submitting"}],
    )
    repo.recover()
    assert repo.get("asset", "a") == a
    interrupted = repo.get("asset", "b")
    assert interrupted["status"] == "analysis_failed" and interrupted["revision"] == 0
    assert interrupted["model_error"] == "request_unknown" and not interrupted["active_job_id"]
    assert repo.get("job", job["id"])["receipts"][0]["status"] == "request_unknown"
    repo.change_asset("b", 0, "trash")


def test_long_recording_does_not_silently_truncate_later_candidates():
    samples = []
    for index in range(205):
        start = index * 4_000_000
        for offset, height in [(0, -0.2), (200_000, 0.6), (400_000, -0.2)]:
            samples.append({"time_us": start + offset, "people_detected": 1, "left": height})
    proposed = propose_candidates(samples, 820_000_000)
    assert len(proposed) == 205
    assert proposed[-1]["peak_us"] == 816_200_000
