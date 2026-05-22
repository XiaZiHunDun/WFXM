#!/usr/bin/env bash
# Install logrotate for Butler gateway log (user-level or system via sudo).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT/scripts/logrotate/butler-gateway.conf"
LOG="$ROOT/logs/butler-gateway.log"
MODE="${1:-user}"

_usage() {
  cat <<EOF
Usage: $(basename "$0") [user|system]

  user    Install to ~/.config/logrotate.d/ (default; no sudo)
  system  sudo cp to /etc/logrotate.d/butler-gateway

After install, test:
  logrotate -d <conf>
EOF
}

_install_user() {
  local conf_dir="${HOME}/.config/logrotate.d"
  local state="${HOME}/.butler/logrotate.state"
  mkdir -p "$conf_dir" "$(dirname "$state")" "$ROOT/logs"
  touch "$LOG"
  sed "s|/home/ailearn/projects/WFXM|$ROOT|g" "$TEMPLATE" >"$conf_dir/butler-gateway"
  echo "Installed user logrotate: $conf_dir/butler-gateway"
  echo "State file: $state"
  echo ""
  echo "Dry-run:"
  logrotate -d -s "$state" "$conf_dir/butler-gateway" 2>&1 | tail -5
  echo ""
  echo "Cron example (daily 03:00):"
  echo "  0 3 * * * logrotate -s $state $conf_dir/butler-gateway"
}

_install_system() {
  local dst="/etc/logrotate.d/butler-gateway"
  mkdir -p "$ROOT/logs"
  touch "$LOG"
  sed "s|/home/ailearn/projects/WFXM|$ROOT|g" "$TEMPLATE" | sudo tee "$dst" >/dev/null
  echo "Installed system logrotate: $dst"
  sudo logrotate -d "$dst" 2>&1 | tail -5 || true
}

case "$MODE" in
  user) _install_user ;;
  system) _install_system ;;
  -h|--help) _usage ;;
  *)
    echo "Unknown mode: $MODE" >&2
    _usage
    exit 1
    ;;
esac
