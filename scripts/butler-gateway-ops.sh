#!/usr/bin/env bash
# Butler WeChat gateway — daily ops (status / restart / logs / preflight / install / upgrade).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/butler-gateway-preflight.sh
source "$ROOT/scripts/lib/butler-gateway-preflight.sh"

UNIT=butler-gateway.service
LOG="$ROOT/logs/butler-gateway.log"

_usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  status      systemd + process + last log lines
  restart     systemctl --user restart $UNIT
  logs        tail -f $LOG
  preflight   check .env, deps, WeChat accounts, linger
  install     install/refresh user systemd unit (see install-butler-gateway-service.sh)
  upgrade     git pull + reinstall unit + restart

Examples:
  bash scripts/butler-gateway-ops.sh status
  bash scripts/butler-gateway-ops.sh preflight
  bash scripts/butler-gateway-ops.sh upgrade
EOF
}

_cmd_status() {
  systemctl --user --no-pager status "$UNIT" 2>&1 | head -20 || true
  echo "---"
  pgrep -af 'butler.main gateway' || echo "(no butler gateway process)"
  echo "---"
  if [[ -f "$LOG" ]]; then
    echo "Last 5 lines of $LOG:"
    tail -5 "$LOG"
  else
    echo "Log not found: $LOG"
  fi
}

_cmd_restart() {
  systemctl --user restart "$UNIT"
  sleep 1
  systemctl --user --no-pager status "$UNIT" | head -12
}

_cmd_logs() {
  mkdir -p "$ROOT/logs"
  touch "$LOG"
  tail -f "$LOG"
}

_cmd_preflight() {
  ROOT="$ROOT" butler_gateway_preflight
}

_cmd_install() {
  exec bash "$ROOT/scripts/install-butler-gateway-service.sh" "$@"
}

_cmd_upgrade() {
  cd "$ROOT"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git pull --ff-only
  else
    echo "Not a git repo; skipping pull" >&2
  fi
  bash "$ROOT/scripts/install-butler-gateway-service.sh"
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    status) _cmd_status ;;
    restart) _cmd_restart ;;
    logs) _cmd_logs ;;
    preflight) _cmd_preflight ;;
    install) _cmd_install "$@" ;;
    upgrade) _cmd_upgrade ;;
    -h|--help|help|"") _usage ;;
    *)
      echo "Unknown command: $cmd" >&2
      _usage
      exit 1
      ;;
  esac
}

main "$@"
