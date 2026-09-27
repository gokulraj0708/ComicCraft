#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$HOME/.venvs/comiccraft"

if ! command -v python >/dev/null 2>&1; then
  echo "Python is missing. In Termux run:"
  echo "pkg update && pkg install python python-pillow rust clang make pkg-config libjpeg-turbo libpng freetype"
  exit 1
fi

mkdir -p "$HOME/.venvs"
python -m venv --system-site-packages "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r "$PROJECT_DIR/requirements-mobile.txt"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
fi

cat <<EOF

ComicCraft Android setup is complete.

Run it with:
  cd "$PROJECT_DIR"
  bash android-run.sh

Then open http://127.0.0.1:8000 in your browser.
EOF
