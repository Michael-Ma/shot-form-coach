"""Bounded, content-free diagnostics for one Codex subprocess.

Never persist raw verbose stderr: it can contain headers, URLs, or request bodies.
Only enumerated network facts and fixed messages cross this boundary.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

DEBUG_LOG_FILTER = (
    "warn,codex_http_client::client=debug,reqwest::connect=debug,"
    "reqwest::connect::verbose=off,hyper_util::client::legacy::connect::http=debug"
)
STDERR_FILE_LIMIT = 131_072
STDERR_LINE_LIMIT = 65_536
TIMELINE_FILE_LIMIT = 262_144


def utc_now():
    return datetime.now(UTC).isoformat()


def network_facts(message):
    """Extract typed failure evidence without echoing any arbitrary message text."""
    text = message.lower() if isinstance(message, str) else ""
    # A field such as is_timeout=false is not a timeout diagnosis.
    flags = {
        key: match.group(1) == "true"
        for key in ("is_timeout", "is_connect")
        if (match := re.search(rf"\b{key}\s*[:=]\s*(true|false)\b", text))
    }
    status = re.search(
        r"\b(?:http(?:\s+status)?|status(?:_code|\s+code)?)\s*[:=]?\s*(?:some\()?([45]\d{2})\b", text
    )
    codes = []
    for pattern, code in [
        (
            r"certificate verify failed|certificate_verify_failed|invalidcertificate|unknownissuer|unknown issuer|certificate has expired",
            "tls_certificate",
        ),
        (
            r"dns error|failed to lookup address|name or service not known|nodename nor servname|dns resolution failed",
            "dns_resolution",
        ),
        (r"connection reset|connectionreset", "connection_reset"),
        (r"connection refused|connectionrefused", "connection_refused"),
        (r"broken pipe|brokenpipe", "broken_pipe"),
        (
            r"tls handshake.*(?:failed|error)|handshakefailure|invalidpeername|tls protocol negotiation failure",
            "tls_handshake",
        ),
        (
            r"proxy authentication required|proxyauthrequired|tunnelunsuccessful|proxy connect.*(?:failed|error)",
            "proxy_connection",
        ),
        (r"http2.*(?:error|failed)|http/2.*(?:error|failed)|goaway|rst_stream", "http2_protocol"),
        (
            r"timed out|\btimedout\b|(?:connect|read|request) timeout (?:expired|exceeded|occurred)",
            "network_timeout",
        ),
    ]:
        if re.search(pattern, text):
            codes.append(code)
    if flags.get("is_timeout") and "network_timeout" not in codes:
        codes.append("network_timeout")
    if flags.get("is_connect") and not codes:
        codes.append("connection_failure")
    if status and not codes:
        codes.append("http_rejection")
    result = {**flags, "causes": codes}
    if status:
        result["http_status"] = int(status[1])
    # OS numbers are useful for support, but paths, addresses, and error bodies are not.
    os_code = re.search(r"(?:os error\s+|\bos\s*\{\s*code:\s*)(\d{1,5})\b", text)
    if os_code:
        result["os_error_code"] = int(os_code[1])
    return result


def stderr_record(line):
    """Return a fixed diagnostic record, never a redacted copy of a raw line."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    text = re.sub(r"\x1b\[[0-9;]*m", "", line)
    lower = text.lower()
    facts = network_facts(text)
    if facts["causes"]:
        record = {"kind": "network_error", **facts}
    elif "error sending request" in lower or "stream disconnected before completion" in lower:
        record = {
            "kind": "network_error",
            "causes": ["request_send_failure"],
            **{key: value for key, value in facts.items() if key != "causes"},
        }
    elif "request failed" in lower:
        record = {"kind": "request_failed", **facts}
    elif "request completed" in lower:
        record = {"kind": "http_response_received"}
        status = re.search(r"\bstatus\s*[:=]\s*([1-5]\d{2})\b", lower)
        if status:
            record["http_status"] = int(status[1])
    elif "starting new connection" in lower or "connecting to" in lower:
        record = {"kind": "connection_started"}
    elif "connected to" in lower:
        record = {"kind": "connection_established"}
    elif "tunneling https" in lower:
        record = {"kind": "proxy_tunnel_started"}
    elif "reading prompt from stdin" in lower:
        record = {"kind": "prompt_read_started"}
    elif "failed to initialize in-process app-server" in lower:
        record = {"kind": "local_startup_failed", "cause": "app_server_initialization"}
    elif "state db discrepancy" in lower and "falling_back" in lower:
        record = {"kind": "local_state_warning", "cause": "state_lookup_fallback"}
    else:
        return None
    # Attribute a failure only from the logger's URL field, not a path mentioned
    # somewhere inside an unrelated error body.
    url_field = re.search(r"\burl\s*[:=]\s*\"?([^\s\"}]+)", text)
    try:
        response_path = urlsplit(url_field[1]).path if url_field else None
    except ValueError:
        response_path = None
    record["request_scope"] = (
        "responses" if response_path in ("/backend-api/codex/responses", "/v1/responses") else "unattributed"
    )
    if record["request_scope"] == "responses":
        request_id = re.search(r"\b(?:x-request-id|request_id)\"?\s*[:=]\s*\"?([a-zA-Z0-9_-]{8,128})\b", text)
        if request_id:
            record["request_id"] = request_id[1]
    stamp = re.search(r"\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\b", text)
    if stamp:
        record["cli_timestamp"] = stamp[1]
    return record


class BoundedJsonLog:
    def __init__(self, path, limit):
        self.stream = path.open("wb")
        self.limit = limit
        self.bytes_written = 0
        self.omitted_records = 0

    def write(self, value):
        encoded = (json.dumps(value, ensure_ascii=False) + "\n").encode()
        if self.bytes_written + len(encoded) > self.limit:
            self.omitted_records += 1
            return
        self.stream.write(encoded)
        self.stream.flush()
        self.bytes_written += len(encoded)

    def close(self):
        self.stream.close()
