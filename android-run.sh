#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$HOME/.venvs/comiccraft"

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "Android environment not found. Run: bash android-setup.sh" >&2
  exit 1
fi

source "$VENV_DIR/bin/activate"
cd "$PROJECT_DIR"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
