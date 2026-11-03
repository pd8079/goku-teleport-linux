#!/bin/sh
set -eu
VENDOR=/app/lib/goku-teleport/vendor
export PYTHONPATH="$VENDOR:/app/lib/goku-teleport${PYTHONPATH:+:$PYTHONPATH}"
export QT_PLUGIN_PATH="$VENDOR/PySide6/Qt/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$VENDOR/PySide6/Qt/plugins/platforms"
exec /usr/bin/python3 -m goku_teleport.app "$@"
