"""Download official model assets; verify publisher/version hashes when recorded."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from app.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Settings.from_env().data_dir / "models")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((Path(__file__).resolve().parents[1] / "models/manifest.json").read_text())
    receipts = {}
    for name, model in manifest.items():
        target = args.output / model["filename"]
        if not target.is_file():
            temp = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(model["url"], timeout=60) as source, temp.open("wb") as dest:
                while chunk := source.read(1024 * 1024):
                    dest.write(chunk)
            temp.replace(target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if model["sha256"] and digest != model["sha256"]:
            raise SystemExit(f"Invalid checksum for {name}")
        if target.stat().st_size < 10000:
            raise SystemExit(f"Model asset {name} is too small")
        receipts[name] = {**model, "sha256": digest, "bytes": target.stat().st_size}
        print(f"{name}: verified {target.stat().st_size} bytes", flush=True)
    (args.output / "download-receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")


if __name__ == "__main__":
    main()
