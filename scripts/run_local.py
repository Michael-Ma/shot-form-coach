"""Launch this project's API and UI; do not stop other projects' listeners."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def available(port):
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(
                f"Port {port} is already in use. Close its existing process or use that instance."
            )


def main():
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
            try:
                with urllib.request.urlopen("http://127.0.0.1:8002/api/health", timeout=2) as response:
                    health = json.load(response)
                if health.get("app") == "shot-form-coach":
                    break
            except (OSError, ValueError):
                time.sleep(1)
        else:
            raise SystemExit("Timed out while waiting for the API.")
        children.append(subprocess.Popen(["npm", "run", "dev"], cwd=ROOT / "web", start_new_session=True))
        print("\nShot Form Coach: http://127.0.0.1:5184/\nPress Ctrl+C to stop this instance.\n", flush=True)
        while all(process.poll() is None for process in children):
            time.sleep(1)
    finally:
        close()


if __name__ == "__main__":
    main()
