#!/usr/bin/env bash
# Daily follow-up bundle: G1-04 window, boundary observability, reasoning trace, EXT-2.
# G1-04 exit 2 before window end is expected (not a failure).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/scripts/lib/butler-source-env.sh" 2>/dev/null || true
  butler_source_env "$ROOT/.env" 2>/dev/null || true
  set +a
fi

fail=0
warn=0

_run() {
  local title="$1"
  shift
  echo ""
  echo "== $title =="
  if "$@"; then
    echo "  -> OK"
    return 0
  fi
  local ec=$?
  echo "  -> FAIL (exit $ec)"
  fail=$((fail + 1))
  return "$ec"
}

_run_warn_ok() {
  local title="$1"
  shift
  echo ""
  echo "== $title =="
  if "$@"; then
    echo "  -> OK"
    return 0
  fi
  local ec=$?
  echo "  -> warn/expected (exit $ec)"
  warn=$((warn + 1))
  return 0
}

echo "Butler ops follow-up check ($(date -Iseconds))"

_run_warn_ok "G1-04 closure / window" bash "$ROOT/scripts/butler-g1-04-closure-check.sh"
_run_warn_ok "G1/G2 boundary observability" bash "$ROOT/scripts/butler-gap-observability.sh"
_run "Reasoning trace smoke" bash "$ROOT/scripts/butler-reasoning-trace-smoke.sh"
_run "DoT-lite smoke" bash "$ROOT/scripts/butler-dot-lite-smoke.sh"
_run "EXT-2 Todoist preflight" bash "$ROOT/scripts/butler-extension-ext2-preflight.sh"

echo ""
echo "summary: fail=$fail warn=$warn"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0
