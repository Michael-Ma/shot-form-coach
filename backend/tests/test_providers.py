import json
from datetime import date

import pytest
from app.billing import estimate_call_cost, pricing_snapshot
from app.codex_runner import call_codex, child_environment, command
from app.config import Settings
from app.contracts import AnalysisConfig
from app.db import Repository
from app.provider import ModelReply, assist


def record():
    return {
        "id": "s",
        "revision": 0,
        "frame_index": [
            {
                "frame_id": str(i),
                "frame_index": i,
                "time_us": i * 100000,
                "source_time_us": i * 100000,
                "path": "unused",
            }
            for i in range(8)
        ],
    }


def config(mode):
    return {**AnalysisConfig().model_dump(), "mode": mode}


def response():
    return {
        "text": json.dumps(
            {
                "last_contact_frame_id": "2",
                "first_clear_frame_id": "3",
                "observations": [
                    {
                        "attribute": "follow_through",
                        "interpretation": "visible_change",
                        "evidence_frame_ids": ["3"],
                    }
                ],
            }
        ),
        "usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30},
    }


def test_codex_receipt_uses_plan_and_keeps_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr("app.provider.codex_status", lambda *_: {"ready": True})
    settings = Settings(tmp_path)
    settings.prepare()
    repo = Repository(settings.db_path)
    job = repo.new_job("analysis", {})
    result = assist(
        settings, repo, job["id"], record(), config("astra_codex"), lambda: False, lambda *_: response()
    )
    receipt = repo.get("job", job["id"])["receipts"][0]
    assert receipt["provider"] == "codex" and receipt["model"] == "gpt-6-astra"
    assert receipt["cost"]["status"] == "subscription_usage" and receipt["cost"]["estimated_usd"] is None
    assert result["release"]["source"] == "astra_codex_visual_candidate"
    assert result["release"]["frame_range"] == [2, 3]


def test_missing_openai_key_fails_before_request_intent(tmp_path):
    settings = Settings(tmp_path)
    settings.prepare()
    repo = Repository(settings.db_path)
    job = repo.new_job("analysis", {})
    with pytest.raises(ValueError, match="openai_key_missing"):
        assist(settings, repo, job["id"], record(), config("astra_api"), lambda: False)
    assert repo.get("job", job["id"])["receipts"] == []


def test_astra_api_usage_includes_reasoning_in_output_only_once():
    snapshot = pricing_snapshot("openai", "gpt-6-astra", date(2026, 10, 8))
    cost = estimate_call_cost(
        snapshot,
        {
            "input_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 200},
            "output_tokens": 100,
            "output_tokens_details": {"reasoning_tokens": 80},
        },
    )
    assert cost["estimated_usd"] == pytest.approx(0.0132)
    long = estimate_call_cost(snapshot, {"input_tokens": 300000, "output_tokens": 100})
    assert long["estimated_usd"] == pytest.approx(6.0075)


def test_codex_command_and_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "never-pass-to-cli")
    monkeypatch.setenv("CODEX_API_KEY", "never-pass-to-cli")
    args = command("/bin/codex", "gpt-6-astra", tmp_path, [{"absolute_path": "/tmp/frame.jpg"}])
    assert "--sandbox" in args and args[args.index("--sandbox") + 1] == "read-only"
    assert "--ignore-user-config" in args and "--ephemeral" in args
    assert "model_providers.sfc-openai.request_max_retries=0" in args
    assert "model_providers.sfc-openai.stream_max_retries=0" in args
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    assert "OPENAI_API_KEY" not in child_environment() and "CODEX_API_KEY" not in child_environment()
    assert args[-1] == "-"


def test_codex_cli_stream_retains_usage_and_reads_structured_reply(monkeypatch, tmp_path):
    # Run a tiny real subprocess emitting the documented JSONL protocol; no remote model call.
    script = tmp_path / "fake-codex"
    script.write_text(
        "#!/usr/bin/env python3\nimport json,sys\nsys.stdin.read()\n"
        'print(json.dumps({"type":"thread.started","thread_id":"t"}),flush=True)\n'
        'print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":'
        'json.dumps({"last_contact_frame_id":None,"first_clear_frame_id":None,"observations":[]})}}),flush=True)\n'
        'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":8}}),flush=True)\n'
    )
    script.chmod(0o755)
    monkeypatch.setattr(
        "app.codex_runner.codex_status",
        lambda *_: {"ready": True, "binary": str(script), "version": "fixture"},
    )
    settings = Settings(tmp_path)
    settings.prepare()
    seen = []
    frames = [{"frame_id": "f", "frame_index": 0, "time_us": 0, "source_time_us": 0, "path": "unused"}]
    result = call_codex(
        settings,
        frames,
        config("astra_codex"),
        {"id": "test", "cancelled": lambda: False, "on_progress": seen.append},
        ModelReply.model_json_schema(),
        "Review.",
    )
    assert result["usage"]["input_tokens"] == 12 and result["turn_completed"]
    assert json.loads(result["text"])["observations"] == []
    assert any(r["usage"] for r in seen)


def test_codex_cancel_kills_child_and_preserves_completed_usage(monkeypatch, tmp_path):
    script = tmp_path / "slow-codex"
    script.write_text(
        "#!/usr/bin/env python3\nimport json,sys,time\nsys.stdin.read()\n"
        'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":8}}),flush=True)\n'
        "time.sleep(20)\n"
    )
    script.chmod(0o755)
    monkeypatch.setattr(
        "app.codex_runner.codex_status",
        lambda *_: {"ready": True, "binary": str(script), "version": "fixture"},
    )
    settings = Settings(tmp_path)
    settings.prepare()
    stop = [False]

    def progress(_):
        stop[0] = True

    from app.codex_runner import CodexCallInterrupted

    with pytest.raises(CodexCallInterrupted) as err:
        call_codex(
            settings,
            [{"frame_id": "f", "frame_index": 0, "time_us": 0, "source_time_us": 0, "path": "unused"}],
            config("astra_codex"),
            {"id": "test", "cancelled": lambda: stop[0], "on_progress": progress},
            ModelReply.model_json_schema(),
            "Review.",
        )
    assert err.value.response["usage"]["input_tokens"] == 12
    assert err.value.response["turn_completed"] is True
