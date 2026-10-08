import json

import pytest
from app.config import Settings
from app.db import Repository
from app.main import create_app
from app.provider import assist, model_reply_schema
from fastapi.testclient import TestClient


def text(en, zh="画面中的观察"):
    return {"en": en, "zh": zh}


def coaching():
    return {
        "overall_summary": text("The visible movement is worth reviewing."),
        "strengths": [],
        "issues": [
            {
                "rubric_id": "coordinated_rise",
                "severity": "high",
                "confidence": "high",
                "title": text("Review the rise"),
                "observation": text("The ball pauses during the rise."),
                "standard_gap": text("Keep the motion comfortable."),
                "why_it_matters": text("It may make the release harder to repeat."),
                "action": text("Use one smooth motion."),
                "drill": text("Try 5 close shots."),
                "evidence_frame_ids": ["f0", "f1"],
                "source_ids": ["curry-mechanics"],
            }
        ],
    }


def asset():
    return {
        "id": "a",
        "revision": 3,
        "created_at": "a",
        "phases": {"release": {"range_us": [0, 100000]}},
        "frame_index": [
            {
                "frame_id": f"f{i}",
                "frame_index": i,
                "time_us": i * 100000,
                "source_time_us": i * 100000,
                "path": "unused",
            }
            for i in range(8)
        ],
        "analysis_config": {"camera_view": "side", "shot_type": "stationary_jump_shot"},
        "preview_path": "unused",
        "original_path": "unused",
        "report": {"id": "old", "video_evidence": [{"large": True}]},
    }


def test_remote_schema_requires_nullable_coaching_and_closed_nested_objects():
    schema = model_reply_schema()
    assert "coaching" in schema["required"]

    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    check(schema)


def test_provider_saves_grounded_context_and_revision_with_model_coaching(tmp_path):
    settings = Settings(tmp_path, api_key="fixture")
    settings.prepare()
    repo = Repository(settings.db_path)
    job = repo.new_job("analysis", {})
    response = {
        "text": json.dumps(
            {
                "last_contact_frame_id": "f0",
                "first_clear_frame_id": "f1",
                "observations": [],
                "coaching": coaching(),
            }
        ),
        "usage": {"prompt_token_count": 100, "candidates_token_count": 10},
    }
    result = assist(
        settings,
        repo,
        job["id"],
        asset(),
        {"mode": "gemini", "max_model_calls": 1, "max_input_frames": 8, "request_timeout_s": 60},
        lambda: False,
        lambda *_: response,
    )
    assert result["asset_revision"] == 3
    assert result["coaching"]["issues"][0]["severity"] == "medium"
    receipt = repo.get("job", job["id"])["receipts"][0]
    assert receipt["coaching_context"]["camera_view"] == "side"
    assert len(receipt["coaching_context"]["rubric"]["dimensions"]) == 5
    assert receipt["coaching_context"]["comparison_scope"].startswith("single attempt")


def test_invalid_coaching_keeps_received_usage(tmp_path):
    settings = Settings(tmp_path, api_key="fixture")
    settings.prepare()
    repo = Repository(settings.db_path)
    job = repo.new_job("analysis", {})
    body = coaching()
    body["issues"][0]["source_ids"] = ["invented-source"]
    response = {
        "text": json.dumps(
            {
                "last_contact_frame_id": None,
                "first_clear_frame_id": None,
                "observations": [],
                "coaching": body,
            }
        ),
        "usage": {"prompt_token_count": 100, "candidates_token_count": 10},
    }
    with pytest.raises(ValueError, match="model_reply_invalid"):
        assist(
            settings,
            repo,
            job["id"],
            asset(),
            {"mode": "gemini", "max_model_calls": 1, "max_input_frames": 8, "request_timeout_s": 60},
            lambda: False,
            lambda *_: response,
        )
    receipt = repo.get("job", job["id"])["receipts"][0]
    assert receipt["status"] == "validation_failed"
    assert receipt["cost"]["status"] == "estimated"
    assert receipt["response"]["usage"]["prompt_token_count"] == 100


def test_public_preview_does_not_rewrite_saved_export_or_submit_model(tmp_path):
    settings = Settings(tmp_path)
    settings.prepare()
    repo = Repository(settings.db_path)
    original = asset()
    repo.put("asset", original)
    with TestClient(create_app(settings, start_worker=False)) as client:
        payload = client.get("/api/assets").json()[0]
    assert payload["coaching"]["status"] == "awaiting_analysis"
    assert "coaching" not in payload["report"]
    assert "video_evidence" not in payload["report"]
    assert repo.get("asset", "a") == original
    assert repo.all("job") == []


def test_valid_narrative_frame_numbers_are_not_mistaken_for_measurement_claims():
    from app.coaching import validate_model_coaching

    body = coaching()
    body["overall_summary"] = {"en": "The ball separates in frame 1.", "zh": "球在第 1 帧分离。"}
    assert validate_model_coaching(body, ["f0", "f1"])["overall_summary"] == body["overall_summary"]
    body["overall_summary"] = {"en": "The ball separates in frame 9.", "zh": "球在第 9 帧分离。"}
    with pytest.raises(ValueError, match="invalid narrative frame evidence"):
        validate_model_coaching(body, ["f0", "f1"])
