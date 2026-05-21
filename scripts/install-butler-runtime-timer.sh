#!/usr/bin/env bash
# Install Butler runtime user systemd timer (灵文1号 pilot).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$(command -v python3)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SVC_T="$ROOT/scripts/systemd/butler-runtime-lingwen.service"
TMR_T="$ROOT/scripts/systemd/butler-runtime-lingwen.timer"
SVC_D="$UNIT_DIR/butler-runtime-lingwen.service"
TMR_D="$UNIT_DIR/butler-runtime-lingwen.timer"

NO_ENABLE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-enable) NO_ENABLE=1 ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--no-enable]"
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
  shift
done

mkdir -p "$UNIT_DIR" "$ROOT/logs"
for pair in "$SVC_T:$SVC_D" "$TMR_T:$TMR_D"; do
  src="${pair%%:*}"
  dst="${pair##*:}"
  sed "s|@WFXM_ROOT@|$ROOT|g; s|@PYTHON@|$PYTHON|g" "$src" >"$dst"
done

systemctl --user daemon-reload
if [[ "$NO_ENABLE" -eq 0 ]]; then
  systemctl --user enable butler-runtime-lingwen.timer
  systemctl --user start butler-runtime-lingwen.timer
fi

echo "Installed: $SVC_D"
echo "         : $TMR_D"
systemctl --user --no-pager list-timers 'butler-runtime*' 2>/dev/null || true
echo ""
echo "Manual: bash scripts/butler-runtime-due.sh"
echo "Logs:   tail -f $ROOT/logs/butler-runtime.log"
