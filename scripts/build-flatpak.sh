#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$ROOT/org.codex.GokuTeleport.yml"
BUILD_DIR="${TMPDIR:-/tmp}/goku-teleport-flatpak-build"
REPO_DIR="${TMPDIR:-/tmp}/goku-teleport-flatpak-repo"
if ! command -v flatpak-builder >/dev/null 2>&1; then
  echo "flatpak-builder is not installed. Install it with your distro's software tools, then rerun this script." >&2
  exit 1
fi
flatpak-builder --user --force-clean --install-deps-from=flathub \
  --repo="$REPO_DIR" "$BUILD_DIR" "$MANIFEST"
flatpak build-bundle "$REPO_DIR" "$ROOT/GokuTeleport.flatpak" org.codex.GokuTeleport
echo "Built $ROOT/GokuTeleport.flatpak"
echo "Install per-user with: flatpak install --user --bundle $ROOT/GokuTeleport.flatpak"
