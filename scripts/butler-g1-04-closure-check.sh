#!/usr/bin/env bash
# G1-04 OT2 observation window closure check (run on/after 2026-06-23).
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
if not w.get("closure_ready"):
    print(
        "G1-04: 窗已结束但 feedback 不足，需人工复核 eval_feedback.jsonl",
        file=sys.stderr,
    )
    raise SystemExit(1)
print("G1-04: closure_ready — 可更新 theory-implementation-gap-register 标 OT2 已证")
PY
