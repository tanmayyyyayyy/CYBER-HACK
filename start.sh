#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "Environment not set up. Run ./setup.sh first." >&2
  exit 1
fi
if [[ ! -d node_modules ]]; then
  echo "Frontend packages are missing. Run ./setup.sh first." >&2
  exit 1
fi
.venv/bin/python scripts/doctor.py
exec .venv/bin/python scripts/run_local.py
