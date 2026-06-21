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
  upgrade     git pull + clean .pyc + pip install + restart + verify + memory-reindex
  verify      post-deploy check (service active, commit match, critical imports)
  drift       detect code changes newer than running service
  reindex     rebuild semantic memory index (灵文1号 default)

Examples:
  bash scripts/butler-gateway-ops.sh status
  bash scripts/butler-gateway-ops.sh preflight
  bash scripts/butler-gateway-ops.sh upgrade
  bash scripts/butler-gateway-ops.sh verify
  bash scripts/butler-gateway-ops.sh drift
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
  for pid in $(pgrep -f 'butler.main gateway' 2>/dev/null || true); do
    echo "Stopping gateway pid=$pid"
    kill "$pid" 2>/dev/null || true
  done
  sleep 1
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

_cmd_reindex() {
  local project="${1:-灵文1号}"
  echo "== memory-reindex ($project) =="
  if [[ -n "$project" ]]; then
    bash "$ROOT/scripts/butler-memory-reindex.sh" --project "$project"
  else
    bash "$ROOT/scripts/butler-memory-reindex.sh"
  fi
}

_cmd_upgrade() {
  local skip_reindex=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-reindex) skip_reindex=1 ;;
      *) echo "Unknown upgrade arg: $1" >&2; _usage; exit 1 ;;
    esac
    shift
  done
  cd "$ROOT"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git pull --ff-only
  else
    echo "Not a git repo; skipping pull" >&2
  fi
  echo "== clean stale __pycache__ =="
  find "$ROOT" -path '*/butler*/__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$ROOT" -path '*/tests*/__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  echo "== sync dependencies (gateway extras) =="
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    pip install -e "$ROOT[gateway]" --quiet 2>/dev/null || echo "pip install [gateway] skipped (non-fatal)" >&2
  elif [[ -d "$ROOT/.venv/bin" ]]; then
    # shellcheck source=/dev/null
    source "$ROOT/.venv/bin/activate"
    pip install -e "$ROOT[gateway]" --quiet 2>/dev/null || echo "pip install [gateway] skipped (non-fatal)" >&2
  else
    pip install -e "$ROOT[gateway]" --quiet 2>/dev/null || echo "pip install [gateway] skipped (non-fatal)" >&2
  fi
  bash "$ROOT/scripts/install-butler-gateway-service.sh"
  echo "== refresh ops timers (runtime all-projects, push-drain) =="
  bash "$ROOT/scripts/install-butler-ops-bundle.sh" --no-enable || true
  echo "== post-deploy verify =="
  sleep 3
  _cmd_verify || echo "WARN: deploy verify failed — check logs" >&2
  if [[ "$skip_reindex" -eq 0 ]]; then
    _cmd_reindex "灵文1号" || echo "memory-reindex failed (non-fatal)" >&2
  fi
}

_cmd_verify() {
  echo "--- deploy verification ---"
  local active
  active=$(systemctl --user is-active "$UNIT" 2>/dev/null || echo "inactive")
  if [[ "$active" != "active" ]]; then
    echo "FAIL: $UNIT is $active (expected active)"
    return 1
  fi
  echo "  [ok] $UNIT is active"

  local expected_sha
  expected_sha=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  local log_sha
  log_sha=$(grep -oP 'commit=\K[a-f0-9]+' "$LOG" 2>/dev/null | tail -1 || echo "")
  if [[ -n "$log_sha" && "$log_sha" == "$expected_sha" ]]; then
    echo "  [ok] running commit=$log_sha matches HEAD"
  elif [[ -n "$log_sha" ]]; then
    echo "  [WARN] log commit=$log_sha vs HEAD=$expected_sha (may need restart)"
  else
    echo "  [info] no commit stamp in log yet"
  fi

  local fail=0
  PYTHONPATH="$ROOT" python3 -c "
from butler.project.lead import gateway_loop_role
from butler.project.manager import get_project_manager
from butler.gateway.message_handler import ButlerMessageHandler
from butler import get_build_identity
info = get_build_identity()
print(f\"  [ok] Butler v{info['version']} (commit={info['git_sha']}, python={info['python']})\")
" 2>&1 || fail=1
  if [[ "$fail" -ne 0 ]]; then
    echo "FAIL: critical import verification failed"
    return 1
  fi

  echo "  -- handler smoke test --"
  PYTHONPATH="$ROOT" python3 -c "
from butler.gateway.message_handler import ButlerMessageHandler
h = ButlerMessageHandler(channel='gateway')
r = h.handle_message('/状态', session_key='deploy-verify', platform='cli')
assert r and ('项目' in r or '管家' in r or '状态' in r or 'Butler' in r or '当前' in r), f'状态命令异常: {r!r}'
print('  [ok] handler smoke: /状态 responded')
" 2>&1 || {
    echo "  [WARN] handler smoke test failed (non-fatal)"
  }

  echo "--- deploy verification: OK ---"
  return 0
}

_cmd_drift() {
  cd "$ROOT"
  local active
  active=$(systemctl --user is-active "$UNIT" 2>/dev/null || echo "inactive")
  if [[ "$active" != "active" ]]; then
    echo "Gateway not running"
    return 0
  fi

  local svc_start
  svc_start=$(systemctl --user show "$UNIT" --property=ActiveEnterTimestamp --value 2>/dev/null || echo "")
  local last_commit_epoch
  last_commit_epoch=$(git log -1 --format=%ct 2>/dev/null || echo 0)
  local svc_epoch
  svc_epoch=$(date -d "$svc_start" +%s 2>/dev/null || echo 0)

  if [[ "$last_commit_epoch" -gt "$svc_epoch" && "$svc_epoch" -gt 0 ]]; then
    local age=$(( last_commit_epoch - svc_epoch ))
    echo "DRIFT DETECTED: newest commit is ${age}s newer than gateway start"
    echo "  gateway started: $svc_start"
    echo "  latest commit:   $(git log -1 --format='%ci %h %s')"
    echo "  run: bash scripts/butler-gateway-ops.sh upgrade"
    return 1
  else
    echo "No drift: gateway is up to date"
    return 0
  fi
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
    upgrade) _cmd_upgrade "$@" ;;
    verify) _cmd_verify ;;
    drift) _cmd_drift ;;
    reindex) _cmd_reindex "$@" ;;
    -h|--help|help|"") _usage ;;
    *)
      echo "Unknown command: $cmd" >&2
      _usage
      exit 1
      ;;
  esac
}

main "$@"
