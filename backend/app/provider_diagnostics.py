"""Evidence-bounded provider failures, safe to show without exposing raw payloads."""

from __future__ import annotations

import json
import re

from .codex_diagnostics import network_facts

NETWORK_CAUSES = {
    "tls_certificate": "TLS certificate verification failed.",
    "dns_resolution": "DNS resolution failed.",
    "connection_reset": "The connection was reset.",
    "connection_refused": "The connection was refused.",
    "broken_pipe": "The connection closed while data was being written.",
    "tls_handshake": "TLS negotiation failed.",
    "proxy_connection": "The proxy connection failed.",
    "http2_protocol": "The HTTP/2 connection reported a protocol error.",
    "network_timeout": "The HTTP client's network timeout expired.",
    "connection_failure": "The HTTP client reported a connection failure.",
    "request_send_failure": "The HTTP client could not finish sending the request.",
}


def with_network_evidence(diagnostic, facts):
    causes = [cause for cause in facts.get("causes", []) if cause in NETWORK_CAUSES]
    if not causes:
        return {**diagnostic, "transport": facts} if facts else diagnostic
    if diagnostic["category"] not in ("unknown", "network", "timeout"):
        return {**diagnostic, "transport": facts}
    cause = causes[0]
    if (
        diagnostic.get("cause") in NETWORK_CAUSES
        and diagnostic["cause"] not in ("connection_failure", "request_send_failure")
        and cause in ("connection_failure", "request_send_failure")
    ):
        return {**diagnostic, "transport": facts}
    return {
        **diagnostic,
        "code": "provider_timeout" if cause == "network_timeout" else "provider_network_error",
        "category": "timeout" if cause == "network_timeout" else "network",
        "cause": cause,
        "detail": NETWORK_CAUSES[cause],
        "transport": facts,
    }


def classify_failure(message="", *, code=None, http_status=None, source="provider"):
    """Classify only explicit error evidence; never publish arbitrary exception text.

    Error bodies can echo credentials or private request input. Public messages are
    fixed, recognized phrases; raw errors are inspected in memory only.
    A connection failure alone cannot establish whether remote usage occurred.
    """
    facts = network_facts(message)
    text = message.lower() if isinstance(message, str) else ""
    text = re.sub(r"\bis_(?:timeout|connect)\s*[:=]\s*(?:true|false)\b", "", text)
    code = code.lower() if isinstance(code, str) else ""
    if not isinstance(http_status, int) or isinstance(http_status, bool):
        match = re.search(r"(?:http(?:\s+status)?|status(?:\s+code)?)\s*[:=]?\s*(\d{3})\b", text)
        http_status = int(match[1]) if match else None
    combined = text + " " + code
    category, public_code, public_message = (
        "unknown",
        "request_unknown",
        "The model call did not return a completed response.",
    )
    if http_status == 429 or any(
        p in combined
        for p in (
            "rate_limit",
            "rate limit",
            "usage limit",
            "insufficient_quota",
            "quota exceeded",
        )
    ):
        category, public_code, public_message = (
            "rate_limit",
            "provider_rate_limited",
            "The provider reported a rate or usage limit.",
        )
    elif http_status in (401, 403) or any(
        p in combined
        for p in (
            "authentication_error",
            "invalid_api_key",
            "incorrect api key",
            "unauthorized",
            "codex_login_required",
            "authentication failed",
            "provider_auth_error",
        )
    ):
        category, public_code, public_message = (
            "authentication",
            "provider_auth_error",
            "The provider rejected authentication or access.",
        )
    elif any(
        p in combined
        for p in (
            "invalid_json_schema",
            "invalid schema",
            "schema validation",
            "provider_schema_error",
        )
    ):
        category, public_code, public_message = (
            "schema",
            "provider_schema_error",
            "The provider rejected the requested output schema.",
        )
    elif http_status == 404 or "model_not_found" in combined or "provider_model_unavailable" in combined:
        category, public_code, public_message = (
            "model",
            "provider_model_unavailable",
            "The requested model or endpoint was unavailable.",
        )
    elif http_status in (400, 413, 415, 422) or any(
        p in combined
        for p in (
            "invalid_request_error",
            "context_length_exceeded",
            "provider_bad_request",
            "provider_rejected",
        )
    ):
        category, public_code, public_message = (
            "request",
            "provider_bad_request",
            "The provider rejected the request.",
        )
    elif (http_status is not None and 500 <= http_status <= 599) or "provider_service_error" in combined:
        category, public_code, public_message = (
            "service",
            "provider_service_error",
            "The provider reported a server error.",
        )
    elif any(p in combined for p in ("timed out", "timeout", "request_timeout")):
        category, public_code, public_message = (
            "timeout",
            "provider_timeout",
            "The model call timed out before completion.",
        )
    elif any(
        p in combined
        for p in (
            "stream disconnected",
            "error sending request",
            "connection reset",
            "connection refused",
            "connection_failed",
            "connectionerror",
            "connecterror",
            "dns error",
            "tls handshake",
            "provider_network_error",
            "certificate verify failed",
            "certificate_verify_failed",
            "sslerror",
        )
    ):
        category, public_code, public_message = (
            "network",
            "provider_network_error",
            "The model connection failed before completion.",
        )
        if "stream disconnected before completion: error sending request" in text:
            # Retain the exact useful error without its potentially private suffix.
            public_message = "stream disconnected before completion: error sending request"
    elif "model_reply_invalid" in combined:
        category, public_code, public_message = (
            "validation",
            "model_reply_invalid",
            "The model response failed local evidence validation.",
        )
    elif "cancelled" in combined:
        category, public_code, public_message = "cancelled", "cancelled", "The model call was cancelled."
    elif "codex_not_installed" in combined or "codex_needs_update" in combined:
        category, public_code, public_message = (
            "setup",
            code,
            "The local Codex CLI is unavailable or needs an update.",
        )
    diagnostic = {
        "code": public_code,
        "category": category,
        "message": public_message,
        "http_status": http_status,
        "source": source,
    }
    return (
        with_network_evidence(diagnostic, facts)
        if facts.get("causes") or "is_timeout" in facts or "is_connect" in facts
        else diagnostic
    )


def event_failure(event):
    if not isinstance(event, dict) or event.get("type") not in ("error", "turn.failed"):
        return None
    error = event.get("error")
    error = error if isinstance(error, dict) else {}
    return classify_failure(
        error.get("message") or event.get("message") or "",
        code=error.get("code") or event.get("code"),
        http_status=error.get("status_code") or event.get("status_code"),
        source="codex_event",
    )


def receipt_diagnostic(settings, receipt):
    """Derive legacy diagnostics without changing the original receipt or billing."""
    response = receipt.get("response") or {}
    diagnostic = receipt.get("diagnostic") or response.get("diagnostic")
    if not diagnostic and receipt.get("provider") == "codex":
        try:
            path = settings.resolve(f"receipts/{receipt['id']}/events.jsonl")
            # A bounded read prevents malformed or huge local logs blocking the UI.
            with path.open("rb") as stream:
                for line in stream.read(1_048_576).splitlines():
                    try:
                        found = event_failure(json.loads(line))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if found and (not diagnostic or found["category"] != "unknown"):
                        diagnostic = found
        except (KeyError, OSError, ValueError):
            pass
    if not diagnostic:
        diagnostic = classify_failure(
            code=receipt.get("error_code") or receipt.get("interruption_reason"),
            http_status=receipt.get("http_status"),
            source="receipt",
        )
    return {
        **diagnostic,
        "receipt_id": receipt.get("id"),
        "analysis_mode": receipt.get("analysis_mode")
        or {"codex": "astra_codex", "openai": "astra_api", "gemini": "gemini"}.get(receipt.get("provider")),
        "outcome_unknown": receipt.get("status") in ("submitting", "request_unknown")
        or receipt.get("outcome") == "unknown",
    }


def with_model_diagnostic(settings, repo, asset):
    """Return a read-only projection of the current revision's failed model call."""
    if not asset.get("model_error"):
        return {key: value for key, value in asset.items() if key != "model_diagnostic"}
    candidates = [
        receipt
        for job in repo.all("job")
        for receipt in job.get("receipts", [])
        if receipt.get("asset_id") == asset["id"] and receipt.get("asset_revision") == asset.get("revision")
    ]
    if candidates:
        receipt = max(candidates, key=lambda value: value.get("submitted_at") or "")
        if receipt.get("status") in ("validated", "received", "submitting"):
            # Do not resurrect an earlier failure after a newer completion or run.
            diagnostic = classify_failure(code=asset["model_error"], source="asset")
        else:
            diagnostic = receipt_diagnostic(settings, receipt)
    else:
        diagnostic = classify_failure(code=asset["model_error"], source="asset")
    return {**asset, "model_diagnostic": diagnostic}
