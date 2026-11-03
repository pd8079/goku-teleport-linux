#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "App environment is missing. Run ./scripts/setup-dev.sh first." >&2
  exit 1
fi
exec .venv/bin/python -m goku_teleport.app "$@"
