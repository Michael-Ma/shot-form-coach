import json

import pytest
from app.config import Settings
from app.contracts import AnalysisConfig
from app.db import Repository
from app.provider import assist, call_sdk


def asset():
    return {
        "id": "shot",
        "revision": 0,
        "frame_index": [{"frame_id": "f0", "time_us": 0, "frame_index": 0, "path": "f.jpg"}],
    }


def config(**extra):
    return {**AnalysisConfig(mode="gemini").model_dump(), **extra}


def valid_response():
    return {
        "text": json.dumps(
            {
                "last_contact_frame_id": None,
                "first_clear_frame_id": None,
                "observations": [],
                "coaching": None,
            }
        ),
        "usage": {"prompt_token_count": 10, "candidates_token_count": 2},
    }


def test_known_client_rejection_is_not_recorded_as_unknown_and_does_not_auto_retry(tmp_path):
    settings = Settings(tmp_path, api_key="fixture")
    settings.prepare()
    repo = Repository(settings.db_path)
    job = repo.new_job("analysis", {})
    calls = []

    class Rejected(Exception):
        code = 400

    def reject(*_):
        calls.append(1)
        raise Rejected()

    with pytest.raises(ValueError, match="provider_bad_request"):
        assist(settings, repo, job["id"], asset(), config(), lambda: False, reject)
    receipt = repo.get("job", job["id"])["receipts"][0]
    assert len(calls) == 1 and receipt["status"] == "provider_rejected" and receipt["http_status"] == 400
    assert receipt["cost"]["estimated_usd"] is None
    # A later explicit job is allowed; the function itself never retried.
    next_job = repo.new_job("analysis", {})
    assist(settings, repo, next_job["id"], asset(), config(), lambda: False, lambda *_: valid_response())


def test_acknowledged_unknown_preserves_uncertain_cost_and_records_explicit_new_intent(tmp_path):
    settings = Settings(tmp_path, api_key="fixture")
    settings.prepare()
    repo = Repository(settings.db_path)
    old = repo.new_job("analysis", {})
    repo.patch(
        "job",
        old["id"],
        status="partial",
        receipts=[
            {
                "id": "prior",
                "asset_id": "shot",
                "provider": "gemini",
                "status": "request_unknown",
                "cost": {"status": "unknown", "estimated_usd": None},
            }
        ],
    )
    new = repo.new_job("analysis", {})
    with pytest.raises(ValueError, match="unresolved_request_blocks_resubmission"):
        assist(settings, repo, new["id"], asset(), config(), lambda: False, lambda *_: valid_response())
    assist(
        settings,
        repo,
        new["id"],
        asset(),
        config(allow_unknown_retry=True),
        lambda: False,
        lambda *_: valid_response(),
    )
    old_receipt = repo.get("job", old["id"])["receipts"][0]
    assert old_receipt["status"] == "retry_authorized"
    assert old_receipt["outcome"] == "unknown"
    assert old_receipt["cost"]["estimated_usd"] is None
    assert old_receipt["retry_authorization"]["new_job_id"] == new["id"]


def test_gemini_uses_json_schema_transport_instead_of_legacy_proto_schema(monkeypatch, tmp_path):
    from google import genai

    (tmp_path / "f.jpg").write_bytes(b"fixture-not-sent")
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def generate_content(self, **kwargs):
            captured.update(kwargs)

            class Response:
                text = "{}"
                usage_metadata = None
                model_version = "fixture"
                response_id = "fixture"

            return Response()

    monkeypatch.setattr(genai, "Client", Client)
    call_sdk(Settings(tmp_path, api_key="fixture"), asset()["frame_index"], config())
    configuration = captured["config"]
    assert configuration.response_schema is None
    assert configuration.response_json_schema["additionalProperties"] is False


def test_unknown_retry_api_blocks_before_creating_a_job_or_changing_revision(tmp_path):
    from app.main import create_app
    from fastapi.testclient import TestClient

    settings = Settings(tmp_path, api_key="fixture")
    settings.prepare()
    repo = Repository(settings.db_path)
    repo.put("asset", asset())
    old = repo.new_job("analysis", {})
    repo.patch(
        "job",
        old["id"],
        status="partial",
        receipts=[{"asset_id": "shot", "provider": "gemini", "status": "request_unknown"}],
    )
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = client.post("/api/analyses", json={"asset_ids": ["shot"], "config": {"mode": "gemini"}})
        assert response.status_code == 409
        assert len(repo.all("job")) == 1 and repo.get("asset", "shot")["revision"] == 0
        response = client.post(
            "/api/analyses",
            json={"asset_ids": ["shot"], "config": {"mode": "gemini", "allow_unknown_retry": True}},
        )
        assert response.status_code == 200 and len(repo.all("job")) == 2
