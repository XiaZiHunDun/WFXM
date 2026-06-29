#!/usr/bin/env bash
# Install weekly + quarterly ops cadence user systemd timers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/butler-systemd-install.sh
source "$ROOT/scripts/lib/butler-systemd-install.sh"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

NO_ENABLE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-enable) NO_ENABLE=1 ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [--no-enable]

Install user timers:
  butler-ops-cadence-weekly.timer     — Sunday 05:00 (G1-04 + agent eval)
  butler-ops-cadence-quarterly.timer  — Jan/Apr/Jul/Oct 1st 05:30 (+ capability archive)

Manual:
  bash $ROOT/scripts/butler-ops-cadence.sh --weekly
  bash $ROOT/scripts/butler-ops-cadence.sh --quarterly
EOF
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
  shift
done

mkdir -p "$UNIT_DIR" "$ROOT/logs"
chmod +x "$ROOT/scripts/butler-ops-cadence.sh"
chmod +x "$ROOT/scripts/lib/butler-systemd-wrap.sh"

_install_pair() {
  local name="$1"
  butler_render_systemd_unit \
    "$ROOT/scripts/systemd/${name}.service" \
    "$UNIT_DIR/${name}.service" \
    "$ROOT"
  butler_render_systemd_unit \
    "$ROOT/scripts/systemd/${name}.timer" \
    "$UNIT_DIR/${name}.timer" \
    "$ROOT"
}

_install_pair butler-ops-cadence-weekly
_install_pair butler-ops-cadence-quarterly

systemctl --user daemon-reload
if [[ "$NO_ENABLE" -eq 0 ]]; then
  systemctl --user enable butler-ops-cadence-weekly.timer
  systemctl --user enable butler-ops-cadence-quarterly.timer
  systemctl --user start butler-ops-cadence-weekly.timer
  systemctl --user start butler-ops-cadence-quarterly.timer
fi

echo "Installed ops cadence timers under $UNIT_DIR"
echo "Logs: $ROOT/logs/butler-ops-cadence-{weekly,quarterly}.log"
systemctl --user --no-pager list-timers 'butler-ops-cadence*' 2>/dev/null || true
