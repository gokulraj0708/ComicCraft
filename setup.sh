#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
if [[ ! -f .env ]]; then cp .env.example .env; fi
printf '\nSetup complete. Run: ./run.sh\nThen open: http://127.0.0.1:8000\n'
