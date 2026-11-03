#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x .venv/bin/pyinstaller ]]; then
  echo "PyInstaller is optional. Install it into .venv with: .venv/bin/python -m pip install pyinstaller" >&2
  exit 1
fi
if ! command -v appimagetool >/dev/null 2>&1; then
  echo "appimagetool is not installed; use the Flatpak build or install appimagetool as a user tool." >&2
  exit 1
fi
.venv/bin/pyinstaller --noconfirm --clean --windowed --name GokuTeleport \
  --collect-all PySide6 --collect-all mediapipe --collect-all cv2 \
  --collect-all pyvirtualcam --add-data "$ROOT/assets/sounds:assets/sounds" launcher.py
APPDIR="$ROOT/dist/GokuTeleport.AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$ROOT/dist/GokuTeleport/." "$APPDIR/usr/bin/"
sed 's/^Exec=goku-teleport$/Exec=AppRun/' "$ROOT/org.codex.GokuTeleport.desktop" \
  > "$APPDIR/usr/share/applications/org.codex.GokuTeleport.desktop"
cp "$APPDIR/usr/share/applications/org.codex.GokuTeleport.desktop" "$APPDIR/org.codex.GokuTeleport.desktop"
cp "$ROOT/assets/icon.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/org.codex.GokuTeleport.svg"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/GokuTeleport" "$@"
EOF
chmod +x "$APPDIR/AppRun"
cp "$ROOT/assets/icon.svg" "$APPDIR/org.codex.GokuTeleport.svg"
ln -sf org.codex.GokuTeleport.svg "$APPDIR/.DirIcon"
appimagetool "$APPDIR" "$ROOT/GokuTeleport-x86_64.AppImage"
