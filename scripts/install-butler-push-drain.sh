#!/usr/bin/env bash
# Install Butler push-queue drain user systemd timer (every 5 min).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/butler-systemd-install.sh
source "$ROOT/scripts/lib/butler-systemd-install.sh"
PYTHON="$(butler_resolve_python3)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SVC_T="$ROOT/scripts/systemd/butler-push-drain.service"
TMR_T="$ROOT/scripts/systemd/butler-push-drain.timer"
SVC_D="$UNIT_DIR/butler-push-drain.service"
TMR_D="$UNIT_DIR/butler-push-drain.timer"

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
  butler_render_systemd_unit "$src" "$dst" "$ROOT" "$PYTHON"
done

systemctl --user daemon-reload
if [[ "$NO_ENABLE" -eq 0 ]]; then
  systemctl --user enable butler-push-drain.timer
  systemctl --user start butler-push-drain.timer
fi

echo "Installed: $SVC_D"
echo "         : $TMR_D"
systemctl --user --no-pager list-timers 'butler-push*' 2>/dev/null || true
echo ""
echo "Manual: butler runtime drain-push"
echo "Logs:   tail -f $ROOT/logs/butler-push-drain.log"
