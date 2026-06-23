#!/usr/bin/env bash
# Daily follow-up bundle: G1-04 window, boundary observability, reasoning trace, EXT verify/sim.
# G1-04 exit 2 before window end is expected; exit 3 = B9-only evidence (skip apply).
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
_run_warn_ok "G1-04 closure apply (if ready)" bash "$ROOT/scripts/butler-g1-04-closure-run-if-ready.sh"
_run_warn_ok "G1/G2 boundary observability" bash "$ROOT/scripts/butler-gap-observability.sh"
_run "P1 live probe" bash "$ROOT/scripts/butler-p1-live-probe.sh"
_run "Reasoning trace smoke" bash "$ROOT/scripts/butler-reasoning-trace-smoke.sh"
_run "DoT-lite smoke" bash "$ROOT/scripts/butler-dot-lite-smoke.sh"
_run "Demo pilot smoke" bash "$ROOT/scripts/butler-demo-pilot-smoke.sh"
_run_warn_ok "Production delegate delta" bash "$ROOT/scripts/butler-prod-delta-observe.sh"
_run "EXT-2 Todoist preflight" bash "$ROOT/scripts/butler-extension-ext2-preflight.sh"
_run_warn_ok "EXT-4 GitHub preflight" bash "$ROOT/scripts/butler-extension-ext4-preflight.sh"
_run "Secrets contract (G1-13)" bash "$ROOT/scripts/butler-secrets-contract-check.sh"
_run_warn_ok "Extension Verify (golden)" bash "$ROOT/scripts/butler-extension-verify.sh"
_run_warn_ok "Extension WeChat sim (handler)" bash "$ROOT/scripts/butler-extension-wechat-sim.sh"
_run_warn_ok "WeChat core sim (handler)" bash "$ROOT/scripts/butler-wechat-core-sim.sh"
_run_warn_ok "WeChat owner sim (manifest)" bash "$ROOT/scripts/butler-wechat-owner-sim.sh" --quick
_run_warn_ok "WeChat dev delegate sim" bash "$ROOT/scripts/butler-wechat-dev-delegate-sim.sh" --quick
_run_warn_ok "Dev delegate experience probe" bash "$ROOT/scripts/butler-dev-delegate-experience-probe.sh"
_run_warn_ok "Dev live flywheel checklist" bash "$ROOT/scripts/butler-dev-live-flywheel-checklist.sh"
_run "Network search route policy" bash "$ROOT/scripts/butler-web-search-route-sim.sh"
_run_warn_ok "Network search route handler" bash "$ROOT/scripts/butler-web-search-route-sim.sh" --handler

echo ""
echo "summary: fail=$fail warn=$warn"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0
