#!/usr/bin/env bash
# G1-04 OT2 observation window — weekly check-in (窗内运营节奏).
#
# During window (06-09 → 07-31): closure-check exit 2 is expected.
# After window: exit 0 only when ot2_closure_ready (production hard feedback).
#
# Usage:
#   bash scripts/butler-g1-04-weekly-checkin.sh
#   bash scripts/butler-g1-04-weekly-checkin.sh --log   # append pilot-log row
#
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

LOG=0
for arg in "$@"; do
  case "$arg" in
    --log) LOG=1 ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh" 2>/dev/null || true
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

STAMP="$(date +%Y-%m-%d)"
FAIL=0
WARN=0

echo "=== G1-04 weekly check-in ($STAMP) ==="

HEADLINE="$(python3 - <<'PY'
from butler.ops.boundary_observability import g1_04_observation_window_status

w = g1_04_observation_window_status()
print(
    f"window {w.get('window_start')}→{w.get('window_end')} "
    f"remaining={w.get('days_remaining')}d "
    f"feedback={w.get('feedback_in_window')} "
    f"production={w.get('feedback_evidence_production')} "
    f"ot2_ready={w.get('ot2_closure_ready')}"
)
PY
)"
echo "$HEADLINE"
echo ""

echo "--- closure check ---"
closure_ec=0
bash "$ROOT/scripts/butler-g1-04-closure-check.sh" || closure_ec=$?
case "$closure_ec" in
  0) echo "  OK: ot2_closure_ready — 可跑 closure-apply" ;;
  2) echo "  OK: 窗未结束（预期 exit 2）" ;;
  3) echo "  WARN: 仅 B9 测评证据 — 需生产硬反馈"; WARN=1 ;;
  1) echo "  FAIL: 窗满但 feedback 不足"; FAIL=1 ;;
  *) echo "  FAIL: closure exit $closure_ec"; FAIL=1 ;;
esac

echo ""
echo "--- prod evidence checklist ---"
evidence_ec=0
bash "$ROOT/scripts/butler-dev-prod-evidence-checklist.sh" || evidence_ec=$?
case "$evidence_ec" in
  0) echo "  OK" ;;
  2) echo "  WARN: 窗内尚无生产来源 eval_feedback"; WARN=1 ;;
  *) echo "  FAIL: evidence checklist exit $evidence_ec"; FAIL=1 ;;
esac

echo ""
echo "--- boundary observability ---"
if bash "$ROOT/scripts/butler-gap-observability.sh"; then
  echo "  OK"
else
  echo "  WARN: boundary observability (non-zero)"
  WARN=1
fi

echo ""
echo "=== pilot-log 建议行 ==="
ROW="| $STAMP | **G1-04 周打卡** | $HEADLINE |"
echo "$ROW"
echo ""
echo "真机补充（每周任选）：/反馈 或 dev 委派 → prod_delegate_* / owner_hard_feedback"
echo "  bash scripts/butler-dev-prod-evidence-checklist.sh"

if [[ "$FAIL" -ne 0 ]]; then
  echo ""
  echo "G1-04 WEEKLY: FAIL"
  exit 1
fi

echo ""
echo "G1-04 WEEKLY: PASS (warn=$WARN)"
if [[ "$LOG" -eq 1 ]]; then
  LOG_FILE="$ROOT/projects/LingWen1/docs/pilot-log.md"
  if [[ -f "$LOG_FILE" ]] && ! grep -q "G1-04 周打卡.*$STAMP" "$LOG_FILE" 2>/dev/null; then
    python3 - <<PY
from pathlib import Path

log_file = Path("$LOG_FILE")
row = "$ROW"
lines = log_file.read_text(encoding="utf-8").splitlines()
for i, line in enumerate(lines):
    if line.startswith("|------|"):
        lines.insert(i + 1, row)
        break
else:
    lines.append(row)
log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
    echo "Appended: $LOG_FILE"
  fi
fi
exit 0
