#!/usr/bin/env bash
# Install/refresh Butler ops units: runtime timer, push-drain, logrotate (+ optional cron).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_LOGROTATE_CRON=0
NO_ENABLE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-logrotate-cron) INSTALL_LOGROTATE_CRON=1 ;;
    --no-enable) NO_ENABLE=1 ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--install-logrotate-cron] [--no-enable]"
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
  shift
done

_enable_args=()
if [[ "$NO_ENABLE" -eq 1 ]]; then
  _enable_args=(--no-enable)
fi

echo "== runtime timer (all projects) =="
bash "$ROOT/scripts/install-butler-runtime-timer.sh" "${_enable_args[@]}"

echo ""
echo "== push queue drain timer =="
bash "$ROOT/scripts/install-butler-push-drain.sh" "${_enable_args[@]}"

echo ""
echo "== eval dataset sync timer (weekly) =="
if [[ -f "$ROOT/scripts/install-butler-eval-sync-timer.sh" ]]; then
  bash "$ROOT/scripts/install-butler-eval-sync-timer.sh" "${_enable_args[@]}"
fi

echo ""
echo "== B9 weekly gate timer (Sunday 03:30) =="
if [[ -f "$ROOT/scripts/install-butler-b9-weekly-timer.sh" ]]; then
  bash "$ROOT/scripts/install-butler-b9-weekly-timer.sh" "${_enable_args[@]}"
fi

echo ""
echo "== logrotate =="
if [[ "$INSTALL_LOGROTATE_CRON" -eq 1 ]]; then
  bash "$ROOT/scripts/install-butler-logrotate.sh" user --install-cron
else
  bash "$ROOT/scripts/install-butler-logrotate.sh" user
fi

echo ""
echo "Ops bundle done. Timers:"
systemctl --user --no-pager list-timers 'butler-*' 2>/dev/null || true
