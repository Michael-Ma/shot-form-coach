import json
import subprocess

import pytest
from app.analysis import compare, measure
from app.config import Settings
from app.contracts import PhaseCorrection
from app.db import Repository
from app.main import create_app
from app.media import ingest, probe
from app.provider import assist
from fastapi.testclient import TestClient


@pytest.fixture
def state(tmp_path):
    settings = Settings(tmp_path, api_key="test-only-placeholder")
    settings.prepare()
    return settings, Repository(settings.db_path)


def asset():
    return {
        "id": "shot_test",
        "revision": 0,
        "created_at": "a",
        "phases": {},
        "frame_index": [
            {
                "frame_index": i,
                "time_us": i * 50000,
                "source_time_us": 1000000 + i * 50000,
                "frame_id": f"frame_{i}",
                "path": "not-needed",
            }
            for i in range(24)
        ],
    }


def test_phase_correction_preserves_original_and_rejects_stale(state):
    _, repo = state
    original = asset()
    original["phases"] = {"release": {"range_us": [100000, 150000]}}
    repo.put("asset", original)
    corrected = repo.correct_phase(
        "shot_test", PhaseCorrection(expected_revision=0, last_contact_frame=4, first_clear_frame=6)
    )
    assert corrected["revision"] == 1
    assert corrected["phases"]["release"]["range_us"] == [200000, 300000]
    assert corrected["phase_history"][0]["previous_phases"] == original["phases"]
    assert repo.update_if_revision("shot_test", 0, report={"old": True}) is None
    with pytest.raises(ValueError, match="stale_revision"):
        repo.correct_phase(
            "shot_test", PhaseCorrection(expected_revision=0, last_contact_frame=4, first_clear_frame=6)
        )


def test_single_frame_correction_retains_uncertainty(state):
    _, repo = state
    repo.put("asset", asset())
    corrected = repo.correct_phase(
        "shot_test", PhaseCorrection(expected_revision=0, last_contact_frame=4, first_clear_frame=4)
    )
    assert corrected["phases"]["release"]["range_us"] == [150000, 250000]


def test_unknown_release_never_becomes_zero_measurement():
    frames = [
        {"time_us": i * 50000, "source_time_us": i * 50000, "frame_id": str(i), "landmarks": None}
        for i in range(20)
    ]
    m = measure({"frames": frames}, {"release": None}, "right", "ambiguous_estimate")
    assert all(v["value"] is None for v in m["measurements"])
    assert set(m["flags"]) >= {"release_unknown", "track_gaps", "handedness_uncertain"}


def test_missing_late_context_and_true_zero_are_distinct():
    points = [{"x": 0.5, "y": 0.5, "visibility": 1} for _ in range(33)]
    for s, h, w in [(11, 23, 15), (12, 24, 16)]:
        points[s] = {"x": 0.5, "y": 0.4, "visibility": 1}
        points[h] = {"x": 0.5, "y": 0.7, "visibility": 1}
        points[w] = {"x": 0.5, "y": 0.1, "visibility": 1}
    frames = [
        {
            "time_us": i * 50000,
            "source_time_us": i * 50000,
            "frame_id": str(i),
            "width": 500,
            "height": 500,
            "landmarks": points,
        }
        for i in range(24)
    ]
    phases = {"release": {"range_us": [100000, 100000]}}
    full = measure({"frames": frames}, phases, "right", "user_setting")
    assert next(v for v in full["measurements"] if v["key"] == "arm_lowering")["value"] == 0
    short = measure({"frames": frames[:12]}, phases, "right", "user_setting")
    assert next(v for v in short["measurements"] if v["key"] == "arm_lowering")["value"] is None
    assert "post_context_short" in short["flags"]


def test_numeric_comparison_requires_matching_context_and_side():
    a = {"id": "a", "analysis_config": {"camera_view": "side", "shot_type": "set_shot"}}
    b = {"id": "b", "revision": 1, "analysis_config": {"camera_view": "front", "shot_type": "set_shot"}}
    metrics = {"side": "right", "measurements": [{"id": "x", "key": "x", "unit": "u", "value": 0}]}
    assert compare(a, metrics, b, metrics, True)["differences"] == []
    b["analysis_config"] = dict(a["analysis_config"])
    assert compare(a, metrics, b, {**metrics, "side": "left"}, True)["differences"] == []
    assert compare(a, metrics, b, metrics)["differences"] == []
    assert compare(a, metrics, b, {**metrics, "side_source": "ambiguous_estimate"}, True)["differences"] == []
    assert compare(a, metrics, b, metrics, True)["differences"][0]["difference"] == 0


def test_idempotency_conflict_and_cancelled_queue(state):
    _, repo = state
    a = repo.new_job("analysis", {"asset_ids": ["a"]}, "intent-1")
    assert repo.new_job("analysis", {"asset_ids": ["a"]}, "intent-1")["id"] == a["id"]
    with pytest.raises(ValueError, match="idempotency_conflict"):
        repo.new_job("analysis", {"asset_ids": ["b"]}, "intent-1")
    repo.patch("job", a["id"], cancel_requested=True)
    assert repo.claim_job() is None


def model_job(repo):
    return repo.new_job("analysis", {})["id"]


def config():
    return {"max_model_calls": 1, "max_input_frames": 8, "request_timeout_s": 1200}


def response(text):
    return {
        "text": text,
        "usage": {"prompt_token_count": 100, "candidates_token_count": 20, "thoughts_token_count": 10},
    }


def test_usage_survives_invalid_json(state):
    settings, repo = state
    key = model_job(repo)
    with pytest.raises(ValueError, match="model_reply_invalid"):
        assist(settings, repo, key, asset(), config(), lambda: False, lambda *_: response("{broken"))
    receipt = repo.get("job", key)["receipts"][0]
    assert receipt["status"] == "validation_failed"
    assert receipt["response"]["usage"]["thoughts_token_count"] == 10
    assert receipt["cost"]["estimated_usd"] > 0


def test_model_cannot_cite_frames_it_did_not_receive(state):
    settings, repo = state
    key = model_job(repo)
    text = json.dumps(
        {"last_contact_frame_id": "invented", "first_clear_frame_id": "frame_23", "observations": []}
    )
    with pytest.raises(ValueError, match="model_reply_invalid"):
        assist(settings, repo, key, asset(), config(), lambda: False, lambda *_: response(text))
    assert repo.get("job", key)["receipts"][0]["cost"]["status"] == "estimated"


def test_unknown_request_has_one_attempt_and_blocks_new_intent(state):
    settings, repo = state
    key = model_job(repo)
    calls = []

    def timeout(*_):
        calls.append(1)
        raise TimeoutError()

    with pytest.raises(ValueError, match="provider_timeout"):
        assist(settings, repo, key, asset(), config(), lambda: False, timeout)
    assert len(calls) == 1
    receipt = repo.get("job", key)["receipts"][0]
    assert receipt["status"] == "request_unknown"
    assert receipt["diagnostic"]["category"] == "timeout"
    assert receipt["cost"]["estimated_usd"] is None
    with pytest.raises(ValueError, match="unresolved_request_blocks_resubmission"):
        assist(settings, repo, model_job(repo), asset(), config(), lambda: False, timeout)
    assert len(calls) == 1


def test_late_cancel_keeps_model_usage(state):
    settings, repo = state
    key = model_job(repo)
    cancelled = [False]

    def deliver(*_):
        cancelled[0] = True
        return response('{"last_contact_frame_id":null,"first_clear_frame_id":null,"observations":[]}')

    with pytest.raises(InterruptedError):
        assist(settings, repo, key, asset(), config(), lambda: cancelled[0], deliver)
    receipt = repo.get("job", key)["receipts"][0]
    assert receipt["status"] == "received_after_cancel"
    assert receipt["cost"]["estimated_usd"] > 0


def test_restart_does_not_repeat_unknown_paid_call(state):
    _, repo = state
    key = model_job(repo)
    repo.patch("job", key, status="running", receipts=[{"asset_id": "shot_test", "status": "submitting"}])
    repo.recover()
    assert repo.get("job", key)["status"] == "partial"
    assert repo.get("job", key)["receipts"][0]["status"] == "request_unknown"
    assert repo.claim_job() is None


def test_api_validation_and_cancel(state):
    settings, repo = state
    repo.put("asset", asset())
    with TestClient(create_app(settings, start_worker=False)) as client:
        # Complete asset DTO needs media fields; exercise jobs only.
        job = client.post("/api/analyses", json={"asset_ids": ["shot_test"], "config": {"mode": "local"}})
        assert job.status_code == 200
        key = job.json()["id"]
        assert client.post(f"/api/jobs/{key}/cancel").json()["status"] == "cancelled"
        assert client.post("/api/analyses", json={"asset_ids": ["shot_test"] * 2}).status_code == 422
        assert client.post("/api/analyses", json={"asset_ids": ["not-found"]}).status_code == 404
        assert client.post("/api/assets/shot_test/reports", json={"expected_revision": 0}).status_code == 422


def test_vfr_import_copies_source_and_preserves_pts(state, tmp_path):
    settings, repo = state
    source = tmp_path / "input.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=128x128:rate=20:duration=0.2",
            "-vf",
            "setpts='if(eq(N,0),0,if(eq(N,1),0.1/TB,if(eq(N,2),0.25/TB,0.5/TB)))'",
            "-fps_mode",
            "passthrough",
            "-enc_time_base",
            "1/1000000",
            "-video_track_timescale",
            "1000000",
            "-c:v",
            "libx264",
            str(source),
        ],
        check=True,
    )
    original = probe(source)[1]
    a = ingest(
        settings, repo, source, "input.mp4", {"source_start_us": 4000000, "source_first_frame_index": 100}
    )
    assert [f["time_us"] for f in a["frame_index"]] == original
    assert probe(settings.resolve(a["preview_path"]))[1] == original
    assert a["frame_index"][2]["source_time_us"] == original[2] + 4000000
    assert a["frame_index"][2]["source_frame_index"] == 102
    assert (
        ingest(
            settings, repo, source, "input.mp4", {"source_start_us": 4000000, "source_first_frame_index": 100}
        )["id"]
        == a["id"]
    )
    source.unlink()
    assert settings.resolve(a["original_path"]).is_file()


def test_reference_correction_invalidates_current_dependent_report(state):
    _, repo = state
    ref = asset()
    repo.put("asset", ref)
    own = {**asset(), "id": "shot_dependent", "report": {"reference_id": ref["id"]}}
    repo.put("asset", own)
    repo.correct_phase(
        ref["id"], PhaseCorrection(expected_revision=0, last_contact_frame=4, first_clear_frame=5)
    )
    assert repo.get("asset", own["id"])["report"] is None
    with pytest.raises(ValueError, match="stale_reference_revision"):
        repo.publish_report(own["id"], 0, {"id": "old"}, {}, ref)


def test_analysis_intent_is_idempotent_across_revision_changes(state):
    _, repo = state
    one = repo.new_job("analysis", {"asset_ids": ["a"], "asset_revisions": {"a": 0}}, "fixed-key")
    two = repo.new_job("analysis", {"asset_ids": ["a"], "asset_revisions": {"a": 1}}, "fixed-key")
    assert one["id"] == two["id"]
