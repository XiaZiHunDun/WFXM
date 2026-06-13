#!/usr/bin/env bash
# Install weekly B9 learning + SWE gate follow-up timer (Sunday 03:30).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SVC_T="$ROOT/scripts/systemd/butler-b9-weekly-gate.service"
TMR_T="$ROOT/scripts/systemd/butler-b9-weekly-gate.timer"
SVC_D="$UNIT_DIR/butler-b9-weekly-gate.service"
TMR_D="$UNIT_DIR/butler-b9-weekly-gate.timer"

NO_ENABLE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-enable) NO_ENABLE=1 ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--no-enable]"
      echo "Timer: Sunday 03:30 — weekly learning; full SWE LIVE when 2-week gate opens."
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
  shift
done

mkdir -p "$UNIT_DIR" "$ROOT/logs"
chmod +x "$ROOT/scripts/butler-b9-weekly-gate-followup.sh"
for pair in "$SVC_T:$SVC_D" "$TMR_T:$TMR_D"; do
  src="${pair%%:*}"
  dst="${pair##*:}"
  sed "s|@WFXM_ROOT@|$ROOT|g" "$src" >"$dst"
done

systemctl --user daemon-reload
if [[ "$NO_ENABLE" -eq 0 ]]; then
  systemctl --user enable butler-b9-weekly-gate.timer
  systemctl --user start butler-b9-weekly-gate.timer
fi

echo "Installed: $SVC_D"
echo "         : $TMR_D"
echo "Manual:  bash $ROOT/scripts/butler-b9-weekly-gate-followup.sh"
systemctl --user --no-pager list-timers 'butler-b9-weekly-gate*' 2>/dev/null || true
