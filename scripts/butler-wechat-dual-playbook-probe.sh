#!/usr/bin/env bash
# B1 灵文1号 · 维护态/新书态双剧本探针
#
# 1) 静态 preflight（无 LLM）：lifecycle、workflow_state、dual-playbook 话术
# 2) 可选 LLM handler sim：dual-playbook.md 各测一句（有 API key 时）
#
# Usage:
#   bash scripts/butler-wechat-dual-playbook-probe.sh
#   bash scripts/butler-wechat-dual-playbook-probe.sh --quick
#   bash scripts/butler-wechat-dual-playbook-probe.sh --static-only
#   bash scripts/butler-wechat-dual-playbook-probe.sh --llm-only
#   bash scripts/butler-wechat-dual-playbook-probe.sh --log
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

STATIC_ONLY=0
LLM_ONLY=0
QUICK=0
LOG=0
for arg in "$@"; do
  case "$arg" in
    --static-only) STATIC_ONLY=1 ;;
    --llm-only) LLM_ONLY=1 ;;
    --quick) QUICK=1 ;;
    --log) LOG=1 ;;
    -h|--help)
      sed -n '1,14p' "$0"
      exit 0
      ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

FAIL=0
STAMP="$(date +%Y-%m-%d)"

if [[ "$LLM_ONLY" -eq 0 ]]; then
  echo "== B1 static preflight =="
  if python3 - <<'PY'
import json
from butler.ops.dual_playbook_probe import run_dual_playbook_static_probe

out = run_dual_playbook_static_probe()
print(json.dumps(out.get("details") or {}, ensure_ascii=False, indent=2))
if not out.get("ok"):
    for err in out.get("errors") or []:
        print(f"  error: {err}")
    raise SystemExit(1)
print("B1 static: OK")
PY
  then
    echo "  OK: static preflight"
  else
    echo "  FAIL: static preflight"
    FAIL=1
  fi
fi

if [[ "$STATIC_ONLY" -eq 0 && "$FAIL" -eq 0 ]]; then
  echo ""
  echo "== B1 WeChat scenario sim (handler + LLM) =="
  _args=(--manifest wechat-dual-playbook-scenarios.yaml)
  if [[ "$QUICK" -eq 1 ]]; then
    _args+=(--quick)
  fi
  export BUTLER_WECHAT_OWNER_SIM="${BUTLER_WECHAT_DUAL_PLAYBOOK_SIM:-1}"
  if bash "$ROOT/scripts/butler-wechat-owner-sim.sh" "${_args[@]}"; then
    echo "  OK: dual-playbook sim"
  else
    _rc=$?
    if [[ "$_rc" -eq 0 ]]; then
      echo "  skip: dual-playbook sim (no LLM key or BUTLER_WECHAT_DUAL_PLAYBOOK_SIM=0)"
    else
      echo "  FAIL: dual-playbook sim"
      FAIL=1
    fi
  fi
fi

echo ""
if [[ "$FAIL" -ne 0 ]]; then
  echo "B1 dual-playbook probe: FAIL"
  exit 1
fi

echo "B1 dual-playbook probe: ALL PASSED"

if [[ "$LOG" -eq 1 ]]; then
  LOG_FILE="$ROOT/projects/LingWen1/docs/pilot-log.md"
  ROW="| $STAMP | **B1 双剧本探针** | butler-wechat-dual-playbook-probe.sh PASS |"
  if [[ -f "$LOG_FILE" ]] && ! grep -q "B1 双剧本探针.*$STAMP" "$LOG_FILE" 2>/dev/null; then
    sed -i "/^|------|/a\\$ROW" "$LOG_FILE"
    echo "Appended: $LOG_FILE"
  fi
fi

exit 0
