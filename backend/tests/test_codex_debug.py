import json
import time

import pytest
from app.codex_diagnostics import STDERR_FILE_LIMIT, network_facts, stderr_record
from app.codex_runner import CodexCallInterrupted, call_codex, child_environment
from app.config import Settings

STREAM_ERROR = "stream disconnected before completion: error sending request"
RESPONSE_URL = "https://chatgpt.com/backend-api/codex/responses"


def setup_cli(monkeypatch, tmp_path, body):
    script = tmp_path / "fake-codex"
    script.write_text("#!/usr/bin/env python3\nimport json,sys,time,os\n" + body)
    script.chmod(0o755)
    monkeypatch.setattr(
        "app.codex_runner.codex_status",
        lambda *_: {"ready": True, "binary": str(script), "version": "fixture"},
    )
    return Settings(tmp_path, codex_debug=True)


def run(settings, instruction="Synthetic test", timeout=5, progress=lambda _: None, cancelled=lambda: False):
    return call_codex(
        settings,
        [],
        {"request_timeout_s": timeout},
        {"id": "test", "cancelled": cancelled, "on_progress": progress},
        {},
        instruction,
    )


def failure_body(lines=(), message=STREAM_ERROR):
    return (
        "sys.stdin.read()\n"
        + "\n".join(f"print({line!r},file=sys.stderr,flush=True)" for line in lines)
        + (
            '\nprint(json.dumps({"type":"thread.started","thread_id":"local-thread"}),flush=True)\n'
            f'print(json.dumps({{"type":"error","message":{message!r}}}),flush=True)\n'
            f'print(json.dumps({{"type":"turn.failed","error":{{"message":{message!r}}}}}),flush=True)\n'
            "sys.exit(1)\n"
        )
    )


def test_child_debug_filters_are_scoped_and_do_not_change_parent_environment(monkeypatch):
    monkeypatch.setenv("RUST_LOG", "trace")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://example.invalid/private")
    normal, debug = child_environment(), child_environment(True)
    assert normal["RUST_LOG"] == "warn"
    assert "codex_http_client::client=debug" in debug["RUST_LOG"]
    assert "codex_core=debug" not in debug["RUST_LOG"]
    assert "::verbose=off" in debug["RUST_LOG"]
    assert not any(key.startswith("OTEL_") for key in debug)
    import os

    assert os.environ["RUST_LOG"] == "trace"


def test_safe_error_diagnostics_keep_timing_and_local_identity_without_private_debug_bytes(
    monkeypatch, tmp_path
):
    secret = "private-request-content bearer-secret /Users/private/photo.jpg data:image/jpeg;base64,SECRET"
    line = (
        f'DEBUG codex_http_client::client: Request failed url="{RESPONSE_URL}?token=secret" '
        f'is_timeout=false is_connect=true error="dns error: failed to lookup address; {secret}"'
    )
    settings = setup_cli(monkeypatch, tmp_path, failure_body([line, secret], STREAM_ERROR + " " + secret))
    seen = []
    with pytest.raises(CodexCallInterrupted) as error:
        run(settings, progress=seen.append)
    result = error.value.response
    assert result["diagnostic"]["cause"] == "dns_resolution"
    assert result["diagnostic"]["category"] == "network"
    assert result["cli_thread_id"] == "local-thread" and result["response_id"] is None
    assert result["started_at"] <= result["finished_at"]
    assert result["interrupted_at"] and result["elapsed_ms"] > 0
    assert seen[-1]["finished_at"] == result["finished_at"]
    folder = tmp_path / "receipts/test"
    for path in folder.glob("*"):
        text = path.read_text()
        assert secret not in text and "bearer-secret" not in text and "token=secret" not in text
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
    assert all(event["_sfc_observed_at"] and event["_sfc_elapsed_ms"] >= 0 for event in events)
    snapshot = json.loads((folder / "diagnostics.json").read_text())
    assert snapshot["diagnostic"] == result["diagnostic"] and "text" not in snapshot


@pytest.mark.parametrize(
    "line",
    [
        "connect timeout=30",
        "request timeout 1200",
        "read timeout: 45",
        "Request failed is_timeout=false is_connect=false",
    ],
)
def test_configuration_or_false_flags_do_not_claim_network_timeout(line):
    assert "network_timeout" not in network_facts(line)["causes"]


def test_some_http_status_is_retained_without_headers():
    line = f'Request failed url="{RESPONSE_URL}" status=Some(503) headers={{"Cookie":"secret"}}'
    result = stderr_record(line)
    assert result["http_status"] == 503 and result["request_scope"] == "responses"
    assert "secret" not in json.dumps(result)


def test_only_response_scoped_request_id_is_retained_from_headers():
    headers = 'headers={"x-request-id": "req_fixture_123", "authorization": "secret"}'
    record = stderr_record(f'Request completed url="{RESPONSE_URL}" status=200 {headers}')
    assert record["request_id"] == "req_fixture_123"
    assert "secret" not in json.dumps(record)
    unrelated = stderr_record(
        f'Request completed url="https://example.invalid/telemetry" status=200 {headers}'
    )
    assert "request_id" not in unrelated
    mentioned = stderr_record(
        f'Request failed url="https://example.invalid/models" status=503 error="Related route {RESPONSE_URL}"'
    )
    assert mentioned["request_scope"] == "unattributed"


@pytest.mark.parametrize(
    "lines,message,expected",
    [
        ([f'Request failed url="{RESPONSE_URL}" is_timeout=false is_connect=false'], STREAM_ERROR, None),
        (
            [f'Request failed url="{RESPONSE_URL}" error="error sending request"'],
            "stream disconnected before completion: InvalidCertificate(UnknownIssuer)",
            "tls_certificate",
        ),
        (
            [
                f'Request failed url="{RESPONSE_URL}" error="InvalidCertificate(UnknownIssuer)"',
                f'Request failed url="{RESPONSE_URL}" error="error sending request"',
            ],
            STREAM_ERROR,
            "tls_certificate",
        ),
        (['Request failed url="https://example.invalid/telemetry" status=503'], STREAM_ERROR, None),
    ],
)
def test_weak_or_unrelated_stderr_cannot_overwrite_specific_model_failure(
    monkeypatch, tmp_path, lines, message, expected
):
    settings = setup_cli(monkeypatch, tmp_path, failure_body(lines, message))
    with pytest.raises(CodexCallInterrupted) as error:
        run(settings)
    result = error.value.response["diagnostic"]
    assert result["code"] == "provider_network_error"
    assert result.get("cause") == expected


def test_stderr_backpressure_and_large_prompt_cannot_deadlock(monkeypatch, tmp_path):
    body = (
        'sys.stderr.write(("starting new connection https://example.invalid/?token=secret\\n")*10000)\n'
        "sys.stderr.flush()\nsys.stdin.read()\n"
        'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":1}}),flush=True)\n'
    )
    settings = setup_cli(monkeypatch, tmp_path, body)
    result = run(settings, instruction="Synthetic prompt. " * 100000, timeout=4)
    assert result["turn_completed"]
    assert result["stderr_capture"]["records_omitted_at_limit"] > 0
    path = tmp_path / "receipts/test/stderr.log"
    assert path.stat().st_size <= STDERR_FILE_LIMIT
    assert "secret" not in path.read_text()


def test_cancellation_works_when_child_stops_reading_large_stdin(monkeypatch, tmp_path):
    settings = setup_cli(
        monkeypatch,
        tmp_path,
        'print(json.dumps({"type":"thread.started","thread_id":"local"}),flush=True)\ntime.sleep(20)\n',
    )
    stop = [False]
    started = time.monotonic()
    with pytest.raises(CodexCallInterrupted) as error:
        run(
            settings,
            instruction="x" * 2000000,
            progress=lambda _: stop.__setitem__(0, True),
            cancelled=lambda: stop[0],
        )
    assert time.monotonic() - started < 3
    assert error.value.reason == "cancelled"
    assert error.value.response["finished_at"] and error.value.response["exit_code"] is not None


def test_timeout_still_applies_after_child_closes_output_pipes(monkeypatch, tmp_path):
    settings = setup_cli(monkeypatch, tmp_path, "os.close(1)\nos.close(2)\ntime.sleep(20)\n")
    with pytest.raises(CodexCallInterrupted) as error:
        run(settings, timeout=0.1)
    response = error.value.response
    assert error.value.reason == "request_timeout"
    assert response["diagnostic"]["cause"] == "application_deadline"
    assert response["finished_at"] and response["interrupted_at"]


def test_process_start_failure_also_has_a_final_diagnostic_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.codex_runner.codex_status",
        lambda *_: {"ready": True, "binary": str(tmp_path / "missing-binary"), "version": "fixture"},
    )
    with pytest.raises(CodexCallInterrupted) as error:
        run(Settings(tmp_path))
    assert error.value.reason == "codex_start_failed"
    assert error.value.response["finished_at"]
    assert (tmp_path / "receipts/test/diagnostics.json").is_file()
