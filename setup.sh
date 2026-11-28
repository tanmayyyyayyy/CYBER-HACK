#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11+ is required." >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Node.js 18+ and npm are required." >&2
  exit 1
fi

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-vision.txt
npm install
.venv/bin/python scripts/download_models.py --insightface --advanced-vision
.venv/bin/python scripts/prepare_demo_feeds.py
echo "Setup complete. Run ./start.sh"
