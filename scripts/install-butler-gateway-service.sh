#!/usr/bin/env bash
# Install Butler gateway as a systemd --user service.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$(command -v python3)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
TEMPLATE="$ROOT/scripts/systemd/butler-gateway.service"
DEST="$UNIT_DIR/butler-gateway.service"

mkdir -p "$UNIT_DIR" "$ROOT/logs"
sed "s|@WFXM_ROOT@|$ROOT|g; s|@PYTHON@|$PYTHON|g" "$TEMPLATE" >"$DEST"
systemctl --user daemon-reload
systemctl --user enable butler-gateway.service
systemctl --user restart butler-gateway.service
systemctl --user --no-pager status butler-gateway.service | head -15
echo "Installed: $DEST"
