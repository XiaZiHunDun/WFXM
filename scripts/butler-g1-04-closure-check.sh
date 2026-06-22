#!/usr/bin/env bash
# G1-04 OT2 observation window closure check (run on/after window end).
#
# Exit codes:
#   0 — ot2_closure_ready (窗满 + ≥1 生产来源硬反馈)
#   1 — 窗满但 feedback 不足
#   2 — 观测窗未结束（开发期预期）
#   3 — 窗满 + feedback≥1，但仅 B9 测评证据（勿当 OT2 已证；可 --pipeline-only apply）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

python3 - <<'PY'
import json
import sys

from butler.ops.boundary_observability import g1_04_observation_window_status

w = g1_04_observation_window_status()
print(json.dumps(w, ensure_ascii=False, indent=2))
print()
if not w.get("window_complete"):
    print(
        f"G1-04: 观测窗未结束（剩 {w.get('days_remaining', '?')} 天），暂不结案",
        file=sys.stderr,
    )
    raise SystemExit(2)
if not w.get("pipeline_closure_ready"):
    print(
        "G1-04: 窗已结束但 feedback 不足，需人工复核 eval_feedback.jsonl",
        file=sys.stderr,
    )
    raise SystemExit(1)
if w.get("feedback_b9_eval_only"):
    print(
        "G1-04: 窗内证据仅 B9 测评（非微信生产用量）— OT2 未证；"
        "延长窗或积累生产硬反馈；管线结案: closure-apply.sh --pipeline-only",
        file=sys.stderr,
    )
    print(
        f"  triggers: {w.get('feedback_triggers_in_window')}",
        file=sys.stderr,
    )
    raise SystemExit(3)
if not w.get("ot2_closure_ready"):
    print("G1-04: 窗满但无生产来源硬反馈", file=sys.stderr)
    raise SystemExit(3)
print("G1-04: ot2_closure_ready — 可更新 gap register（含生产硬反馈）")
PY
