#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_BIN="${XDG_BIN_HOME:-${HOME:?}/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-${HOME:?}/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-${HOME:?}/.local/share}/icons/hicolor/scalable/apps"
mkdir -p "$LOCAL_BIN" "$APP_DIR" "$ICON_DIR"
cat > "$LOCAL_BIN/goku-teleport" <<EOF
#!/usr/bin/env bash
exec "$ROOT/run.sh" "\$@"
EOF
chmod +x "$LOCAL_BIN/goku-teleport"
cp "$ROOT/assets/icon.svg" "$ICON_DIR/org.codex.GokuTeleport.svg"
sed "s#^Exec=.*#Exec=\"$LOCAL_BIN/goku-teleport\"#; s#^Icon=.*#Icon=$ICON_DIR/org.codex.GokuTeleport.svg#" \
  "$ROOT/org.codex.GokuTeleport.desktop" > "$APP_DIR/org.codex.GokuTeleport.desktop"
echo "Installed a per-user launcher at $APP_DIR/org.codex.GokuTeleport.desktop"
echo "This did not install system packages or change system settings."
