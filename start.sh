#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for command_name in uv npm ffmpeg ffprobe; do
  command -v "$command_name" >/dev/null || { echo "Install $command_name and rerun ./start.sh"; exit 1; }
done
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env. Local vision and signed-in Codex work without API keys."
fi
uv sync --locked --extra dev --python 3.12
lock_digest=$(.venv/bin/python -c 'import hashlib;print(hashlib.sha256(open("web/package-lock.json","rb").read()).hexdigest())')
lock_stamp=web/node_modules/.sfc-lock-digest
if [[ ! -f "$lock_stamp" ]] || [[ "$(cat "$lock_stamp")" != "$lock_digest" ]]; then
  npm ci --prefix web
  printf '%s\n' "$lock_digest" > "$lock_stamp"
fi
.venv/bin/python scripts/download_models.py
exec .venv/bin/python scripts/run_local.py "$@"
