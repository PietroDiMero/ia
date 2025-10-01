#!/usr/bin/env bash
set -euo pipefail

# Resolve project root (this script is in scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR%/scripts}"
cd "$ROOT_DIR"

# Optional env: source .env if present (contains e.g. OPENAI_API_KEY)
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

# Create venv if missing
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

# Install deps (idempotent)
python3 -m pip install --upgrade pip >/dev/null 2>&1 || true
python3 -m pip install -r requirements.txt >/dev/null 2>&1 || true

mkdir -p logs

# Start the server; rotate simple logs (optional)
LOG_OUT="logs/server.out"
LOG_ERR="logs/server.err"
stamp() { date "+%Y-%m-%d %H:%M:%S"; }
{
  echo "[$(stamp)] Starting uvicorn on 127.0.0.1:8000";
  exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} >>"$LOG_OUT" 2>>"$LOG_ERR"
