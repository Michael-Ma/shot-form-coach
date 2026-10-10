import json

import pytest
from app.coaching import build_review
from app.codex_runner import CodexCallInterrupted, call_codex
from app.config import Settings
from app.contracts import AnalysisConfig
from app.db import Repository
from app.provider import assist
from app.provider_diagnostics import classify_failure, event_failure, with_model_diagnostic

NETWORK_MESSAGE = "stream disconnected before completion: error sending request"


def test_cli_error_events_keep_safe_specific_reason_and_no_completion(monkeypatch, tmp_path):
    script = tmp_path / "fake-codex"
    script.write_text(
        "#!/usr/bin/env python3\nimport json,sys\nsys.stdin.read()\n"
        'print(json.dumps({"type":"thread.started","thread_id":"t"}),flush=True)\n'
        f'print(json.dumps({{"type":"error","message":{NETWORK_MESSAGE!r}}}),flush=True)\n'
        f'print(json.dumps({{"type":"turn.failed","error":{{"message":{NETWORK_MESSAGE!r}}}}}),flush=True)\n'
        "sys.exit(1)\n"
    )
    script.chmod(0o755)
    monkeypatch.setattr(
        "app.codex_runner.codex_status",
        lambda *_: {"ready": True, "binary": str(script), "version": "fixture"},
    )
    seen = []
    with pytest.raises(CodexCallInterrupted) as error:
        call_codex(
            Settings(tmp_path),
            [],
            AnalysisConfig().model_dump(),
            {"id": "call", "cancelled": lambda: False, "on_progress": seen.append},
            {"type": "object"},
            "Synthetic fixture.",
        )
    response = error.value.response
    assert response["diagnostic"]["code"] == "provider_network_error"
    assert response["diagnostic"]["message"] == NETWORK_MESSAGE
    assert response["diagnostic"]["http_status"] is None
    assert not response["turn_completed"] and response["exit_code"] == 1
    assert response["usage"] == {} and response["text"] == ""
    assert seen[-1]["diagnostic"] == response["diagnostic"]
    assert response["request_metadata"]["automatic_retries"] == 0


def test_exit_zero_without_terminal_event_is_still_unknown(monkeypatch, tmp_path):
    script = tmp_path / "fake-codex"
    script.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.read()\nprint('[]')\n")
    script.chmod(0o755)
    monkeypatch.setattr(
        "app.codex_runner.codex_status",
        lambda *_: {"ready": True, "binary": str(script), "version": "fixture"},
    )
    with pytest.raises(CodexCallInterrupted) as error:
        call_codex(
            Settings(tmp_path),
            [],
            AnalysisConfig().model_dump(),
            {"id": "call", "cancelled": lambda: False, "on_progress": lambda _: None},
            {},
            "Synthetic fixture.",
        )
    assert error.value.response["exit_code"] == 0
    assert error.value.response["diagnostic"]["code"] == "request_unknown"


@pytest.mark.parametrize(
    ("message", "code", "category"),
    [
        ("unexpected status 429 Too Many Requests", None, "rate_limit"),
        ("unexpected status 401 Unauthorized", None, "authentication"),
        ("Invalid schema for response_format", None, "schema"),
        ("unexpected HTTP status 503", None, "service"),
        ("", "model_reply_invalid", "validation"),
        ("", "request_timeout", "timeout"),
        (NETWORK_MESSAGE, None, "network"),
        ("", "provider_auth_error", "authentication"),
        ("unexplained provider exit", None, "unknown"),
    ],
)
def test_failure_categories_are_based_on_specific_evidence(message, code, category):
    assert classify_failure(message, code=code)["category"] == category


def test_public_diagnostics_do_not_echo_credentials_urls_or_request_content():
    private = "Bearer sk-secret-key https://private.example/?token=secret /Users/private/image.jpg prompt"
    for message in [private, NETWORK_MESSAGE + ": " + private, "Invalid schema: " + private]:
        diagnostic = event_failure({"type": "turn.failed", "error": {"message": message}})
        assert private not in json.dumps(diagnostic)
        assert "sk-secret" not in json.dumps(diagnostic)
    assert event_failure({"type": "item.completed", "item": {"text": private}}) is None


def test_specific_network_error_preserves_unknown_receipt_and_does_not_retry(monkeypatch, tmp_path):
    monkeypatch.setattr("app.provider.codex_status", lambda *_: {"ready": True})
    settings = Settings(tmp_path)
    settings.prepare()
    repo = Repository(settings.db_path)
    job = repo.new_job("analysis", {})
    calls = []

    def fail(*_):
        calls.append(1)
        raise CodexCallInterrupted(
            "codex_call_failed",
            {
                "usage": {},
                "turn_completed": False,
                "diagnostic": classify_failure(NETWORK_MESSAGE),
            },
        )

    with pytest.raises(ValueError, match="^provider_network_error$"):
        assist(
            settings,
            repo,
            job["id"],
            {"id": "shot", "revision": 4, "frame_index": []},
            AnalysisConfig(mode="astra_codex").model_dump(),
            lambda: False,
            fail,
        )
    receipt = repo.get("job", job["id"])["receipts"][0]
    assert calls == [1]
    assert receipt["status"] == "request_unknown"
    assert receipt["cost"]["estimated_usd"] is None
    assert receipt["error_code"] == "provider_network_error"
    with pytest.raises(ValueError, match="unresolved_request_blocks_resubmission"):
        assist(
            settings,
            repo,
            repo.new_job("analysis", {})["id"],
            {"id": "shot", "revision": 4, "frame_index": []},
            AnalysisConfig(mode="astra_codex").model_dump(),
            lambda: False,
            fail,
        )
    assert calls == [1]


def test_legacy_log_diagnosis_is_revision_scoped_and_does_not_mutate_history(tmp_path):
    settings = Settings(tmp_path)
    settings.prepare()
    repo = Repository(settings.db_path)
    job = repo.new_job("analysis", {})
    receipt = {
        "id": "call_old",
        "provider": "codex",
        "asset_id": "shot",
        "asset_revision": 4,
        "status": "request_unknown",
        "response": {"provider_error": True},
        "cost": {"status": "unknown", "estimated_usd": None},
    }
    repo.patch("job", job["id"], receipts=[receipt])
    folder = tmp_path / "receipts" / "call_old"
    folder.mkdir()
    (folder / "events.jsonl").write_text(json.dumps({"type": "error", "message": NETWORK_MESSAGE}) + "\n")
    asset = {"id": "shot", "revision": 4, "model_error": "request_unknown", "frame_index": []}
    projected = with_model_diagnostic(settings, repo, asset)
    assert projected["model_diagnostic"]["category"] == "network"
    assert projected["model_diagnostic"]["outcome_unknown"]
    assert projected["model_diagnostic"]["analysis_mode"] == "astra_codex"
    assert "model_diagnostic" not in asset
    assert repo.get("job", job["id"])["receipts"] == [receipt]
    next_revision = with_model_diagnostic(settings, repo, {**asset, "revision": 5})
    assert next_revision["model_diagnostic"]["category"] == "unknown"
    succeeded = with_model_diagnostic(settings, repo, {**projected, "model_error": None})
    assert "model_diagnostic" not in succeeded


def test_failed_review_without_measurements_describes_connection_not_video():
    diagnostic = {**classify_failure(NETWORK_MESSAGE), "outcome_unknown": True}
    review = build_review(
        {
            "id": "shot",
            "revision": 4,
            "model_error": "request_unknown",
            "frame_index": [],
            "model_diagnostic": diagnostic,
        }
    )
    assert review["outcome"] == "model_failed"
    assert review["version"] == "human-review-v4"
    assert review["overall"]["headline"]["zh"] == "视觉模型连接中断"
    assert "连接断开" in review["overall"]["summary"]["zh"]
    assert "是否产生用量仍未知" in review["empty_state"]["detail"]["zh"]
    assert "视频" not in review["overall"]["summary"]["zh"]
    assert review["model_diagnostic"]["message"] == NETWORK_MESSAGE


def test_failed_rerun_does_not_apply_a_previous_revision_coaching():
    review = build_review(
        {
            "id": "shot",
            "revision": 5,
            "model_error": "provider_network_error",
            "frame_index": [],
            "model_assist": {"asset_revision": 4, "coaching": {"overall_summary": "previous review"}},
        }
    )
    assert review["outcome"] == "model_failed"
    assert review["assessment_source"] == "measurements"
    assert review["coverage"]["model_review"] == "failed"
    assert any("较早版本" in item["zh"] for item in review["limitations"])
