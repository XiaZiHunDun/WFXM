#!/usr/bin/env bash
# Install weekly WeChat → LangFuse dataset sync timer (O8).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/butler-systemd-install.sh
source "$ROOT/scripts/lib/butler-systemd-install.sh"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SVC_T="$ROOT/scripts/systemd/butler-eval-sync.service"
TMR_T="$ROOT/scripts/systemd/butler-eval-sync.timer"
SVC_D="$UNIT_DIR/butler-eval-sync.service"
TMR_D="$UNIT_DIR/butler-eval-sync.timer"

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
chmod +x "$ROOT/scripts/lib/butler-systemd-wrap.sh"
for pair in "$SVC_T:$SVC_D" "$TMR_T:$TMR_D"; do
  src="${pair%%:*}"
  dst="${pair##*:}"
  butler_render_systemd_unit "$src" "$dst" "$ROOT"
done

systemctl --user daemon-reload
if [[ "$NO_ENABLE" -eq 0 ]]; then
  systemctl --user enable butler-eval-sync.timer
  systemctl --user start butler-eval-sync.timer
fi

echo "Installed: $SVC_D"
echo "         : $TMR_D"
systemctl --user --no-pager list-timers 'butler-eval-sync*' 2>/dev/null || true
