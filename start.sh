#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "Python 3.11+ is required. Run ./setup.sh first." >&2
  exit 1
fi
if [[ ! -d node_modules ]]; then
  echo "Frontend packages are missing. Run ./setup.sh first." >&2
  exit 1
fi
"$PY" scripts/doctor.py
exec "$PY" scripts/run_local.py
