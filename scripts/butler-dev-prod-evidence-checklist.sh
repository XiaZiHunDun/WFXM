#!/usr/bin/env bash
# G1-04 + dev flywheel production evidence checklist (read-only).
#
# Usage:
#   bash scripts/butler-dev-prod-evidence-checklist.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

python3 - <<'PY'
import json
import os
import sys

from butler.ops.boundary_observability import g1_04_observation_window_status
from butler.ops.delegate_failure_capture import failure_audit_summary
from butler.ops.g1_04_prod_evidence import prod_evidence_enabled
from butler.ops.prod_experience_effectiveness import load_dev_delegate_outcomes

print("=== Dev production evidence · G1-04 checklist ===")
print()

pe = prod_evidence_enabled()
cap = os.getenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "").strip() or "(unset)"
print(f"1. BUTLER_EVAL_PROD_EVIDENCE={'on' if pe else 'off'}")
print(f"   BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES={cap}")
if not pe:
    print("   ACTION: set BUTLER_EVAL_PROD_EVIDENCE=1 (default on)")

g1 = g1_04_observation_window_status()
print()
print(f"2. G1-04 window {g1.get('window_start')} → {g1.get('window_end')}")
print(
    f"   feedback_in_window={g1.get('feedback_in_window')} "
    f"production={g1.get('feedback_evidence_production')} "
    f"b9_only={g1.get('feedback_b9_eval_only')}"
)
print(f"   ot2_closure_ready={g1.get('ot2_closure_ready')} days_remaining={g1.get('days_remaining')}")

triggers = g1.get("feedback_triggers_in_window") or {}
prod_triggers = [t for t in triggers if t and not str(t).startswith("b9_")]
if prod_triggers:
    print(f"   production triggers: {prod_triggers}")
else:
    print("   ACTION: 真机微信 dev 委派（非 B9）成功/失败各至少 1 次 → eval_feedback prod_delegate_*")

outcomes = load_dev_delegate_outcomes(limit=200)
prod_out = [r for r in outcomes if r.get("capture_source") == "delegate_pipeline"]
print()
print(f"3. delegate_dev_outcomes.jsonl pipeline rows: {len(prod_out)}")
if prod_out:
  last = prod_out[-1]
  print(
      f"   last: project={last.get('project')} success={last.get('success')} "
      f"verify={last.get('verify_passed')}"
  )

fail = failure_audit_summary()
print()
print(f"4. delegate_failures audit total={fail.get('total')} path={fail.get('audit_path')}")

print()
print("=== 真机话术（灵文1号 · 生产证据）===")
print("  A. /切换 灵文1号")
print("  B. 「请委派开发：在 docs 写 dev-flywheel-{date}.md 一行验收戳，read_file 确认」")
print("  C. 成功后期望 eval_feedback trigger=prod_delegate_verify_pass")
print("  D. 若 verify 失败，期望 prod_delegate_failure + L3 PROD_FAIL_*")
print()
print("守门:")
print("  bash scripts/butler-dev-live-flywheel-checklist.sh --probe")
print("  bash scripts/butler-g1-04-closure-check.sh  # 窗满后")
print()

production = int(g1.get("feedback_evidence_production") or 0)
warn = 0
if production < 1 and int(g1.get("days_remaining") or 0) < 60:
    print("WARN: G1-04 窗内尚无生产来源 eval_feedback（仅 B9 不够 OT2 结案）")
    warn = 1
if production >= 1:
    print("OK: 窗内已有生产来源硬反馈")
elif warn:
    sys.exit(2)
else:
    print("OK: checklist complete (production evidence still accumulating)")
PY
