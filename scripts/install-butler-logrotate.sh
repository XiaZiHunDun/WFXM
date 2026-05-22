#!/usr/bin/env bash
# Install logrotate for Butler gateway log (user-level or system via sudo).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT/scripts/logrotate/butler-gateway.conf"
LOG="$ROOT/logs/butler-gateway.log"
MODE="user"
INSTALL_CRON=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    user|system) MODE="$1" ;;
    --install-cron) INSTALL_CRON=1 ;;
    -h|--help) MODE="help" ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
  shift
done

_usage() {
  cat <<EOF
Usage: $(basename "$0") [user|system] [--install-cron]

  user    Install to ~/.config/logrotate.d/ (default; no sudo)
  system  sudo cp to /etc/logrotate.d/butler-gateway
  --install-cron  Append daily 03:00 user crontab entry (user mode)

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
  local cron_line="0 3 * * * logrotate -s $state $conf_dir/butler-gateway"
  if [[ "$INSTALL_CRON" -eq 1 ]]; then
    _install_cron_line "$cron_line"
  else
    echo "Cron example (daily 03:00):"
    echo "  $cron_line"
    echo "  或: $0 user --install-cron"
  fi
}

_install_cron_line() {
  local line="$1"
  local tmp
  tmp="$(mktemp)"
  (crontab -l 2>/dev/null || true) | grep -Fv "butler-gateway" | grep -Fv "logrotate.d/butler-gateway" >"$tmp" || true
  echo "$line" >>"$tmp"
  crontab "$tmp"
  rm -f "$tmp"
  echo "Installed user crontab entry:"
  echo "  $line"
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
  help|-h|--help) _usage ;;
  *)
    echo "Unknown mode: $MODE" >&2
    _usage
    exit 1
    ;;
esac
