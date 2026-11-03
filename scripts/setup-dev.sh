#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then
  echo "Python 3.10 or newer is required. Set PYTHON_BIN to a compatible interpreter." >&2
  exit 1
fi
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo "Setup complete. Start with: ./run.sh"
