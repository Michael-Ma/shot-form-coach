#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for command_name in uv npm ffmpeg ffprobe; do
  command -v "$command_name" >/dev/null || { echo "Install $command_name and rerun ./start.sh"; exit 1; }
done
uv sync --locked --extra dev --python 3.12
if [[ ! -d web/node_modules ]]; then
  npm ci --prefix web
fi
.venv/bin/python scripts/download_models.py
exec .venv/bin/python scripts/run_local.py
