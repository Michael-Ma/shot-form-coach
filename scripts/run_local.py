"""Launch the API, worker and UI together, with model readiness checks."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_URL = "http://127.0.0.1:8002/api/health"
UI_URL = "http://127.0.0.1:5184/"


def health():
    try:
        with urllib.request.urlopen(API_URL, timeout=2) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def check():
    from app.codex_runner import codex_status
    from app.config import Settings

    settings = Settings.from_env()
    print("Gemini:", "API key configured" if settings.api_key else "API key not configured")
    print("Astra API:", "API key configured" if settings.openai_api_key else "API key not configured")
    codex = codex_status(settings.codex_bin)
    print("Astra through Codex:", "ready (ChatGPT sign-in)" if codex["ready"] else codex["reason"])
    print(
        "Vision models:",
        "ready"
        if all(
            (settings.data_dir / "models" / name).is_file()
            for name in ["pose_landmarker_full.task", "yolox_s.onnx"]
        )
        else "not downloaded",
    )
    return codex


def available(port):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(f"Port {port} is in use. Stop the existing instance with Ctrl+C and rerun.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Check models and credentials without starting servers"
    )
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser automatically")
    args = parser.parse_args()
    check()
    if args.check:
        return
    existing = health()
    if existing and existing.get("app") == "shot-form-coach" and existing.get("version") == "0.7.0":
        try:
            with urllib.request.urlopen(UI_URL, timeout=2):
                pass
            print("Shot Form Coach is already running:", UI_URL)
            if not args.no_open:
                webbrowser.open(UI_URL)
            return
        except OSError:
            pass
    for port in [8002, 5184]:
        available(port)
    children = []

    def close(*_):
        for process in reversed(children):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in children:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, close)
    signal.signal(signal.SIGTERM, close)
    try:
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8002",
                    "--log-level",
                    "warning",
                ],
                cwd=ROOT,
                start_new_session=True,
            )
        )
        for _ in range(120):
            if children[0].poll() is not None:
                raise SystemExit("The API did not start. Inspect the error above.")
            ready = health()
            if ready and ready.get("app") == "shot-form-coach":
                break
            time.sleep(1)
        else:
            raise SystemExit("Timed out while waiting for the API.")
        children.append(subprocess.Popen(["npm", "run", "dev"], cwd=ROOT / "web", start_new_session=True))
        for _ in range(60):
            if children[1].poll() is not None:
                raise SystemExit("The interface did not start. Inspect the error above.")
            try:
                with urllib.request.urlopen(UI_URL, timeout=2):
                    break
            except OSError:
                time.sleep(1)
        else:
            raise SystemExit("Timed out while waiting for the interface.")
        print(
            "\nShot Form Coach:",
            UI_URL,
            "\nAPI + background worker + UI are ready. Ctrl+C stops this instance.\n",
            flush=True,
        )
        if not args.no_open:
            webbrowser.open(UI_URL)
        while all(process.poll() is None for process in children):
            time.sleep(1)
    finally:
        close()


if __name__ == "__main__":
    main()
