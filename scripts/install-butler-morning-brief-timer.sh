#!/usr/bin/env bash
# Install Butler morning-brief user systemd timer (opt-in: BUTLER_MORNING_BRIEF=1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SVC_T="$ROOT/scripts/systemd/butler-morning-brief.service"
TMR_T="$ROOT/scripts/systemd/butler-morning-brief.timer"
SVC_D="$UNIT_DIR/butler-morning-brief.service"
TMR_D="$UNIT_DIR/butler-morning-brief.timer"

NO_ENABLE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-enable) NO_ENABLE=1 ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--no-enable]"
      echo "Requires BUTLER_MORNING_BRIEF=1 in .env for pushes to send."
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
  shift
done

mkdir -p "$UNIT_DIR" "$ROOT/logs"
chmod +x "$ROOT/scripts/butler-morning-brief-push.sh"
for pair in "$SVC_T:$SVC_D" "$TMR_T:$TMR_D"; do
  src="${pair%%:*}"
  dst="${pair##*:}"
  sed "s|@WFXM_ROOT@|$ROOT|g" "$src" >"$dst"
done

systemctl --user daemon-reload
if [[ "$NO_ENABLE" -eq 0 ]]; then
  systemctl --user enable butler-morning-brief.timer
  systemctl --user start butler-morning-brief.timer
fi

echo "Installed: $SVC_D"
echo "         : $TMR_D"
systemctl --user --no-pager list-timers 'butler-morning-brief*' 2>/dev/null || true
echo ""
echo "Opt-in: set BUTLER_MORNING_BRIEF=1 in .env"
echo "Manual: bash scripts/butler-morning-brief-push.sh"
echo "Logs:   tail -f $ROOT/logs/butler-morning-brief.log"
