#!/usr/bin/env bash
# G1/G2 honest-boundary observability gate (read-only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<'PY'
import json
import sys

from butler.ops.boundary_observability import (
    boundary_observability_summary,
    collect_boundary_observations,
)

obs = collect_boundary_observations()
summary = boundary_observability_summary()
print("=== G1/G2 boundary observability ===")
for o in obs:
    print(o.line(verbose=True))
print()
print(json.dumps(summary, ensure_ascii=False, indent=2))
try:
    from butler.ops import runtime_metrics

    print()
    print("=== Structured events (global) ===")
    snap = runtime_metrics.snapshot_global()
    counters = snap.get("counters") or {}
    for key in sorted(counters):
        if key.startswith("structured_event_") or "retrieval_degraded" in key or "llm_api_call" in key:
            print(f"  {key}: {counters[key]}")
except Exception as exc:
    print(f"(structured metrics skipped: {exc})")
g1 = summary.get("g1_04_window") or {}
if g1:
    print()
    print("=== G1-04 OT2 observation window ===")
    print(
        f"  window: {g1.get('window_start')} → {g1.get('window_end')} "
        f"(today={g1.get('today')}, remaining={g1.get('days_remaining')}d)"
    )
    print(
        f"  feedback: in_window={g1.get('feedback_in_window')} "
        f"7d={g1.get('feedback_7d')} actions={g1.get('feedback_actions_in_window')}"
    )
    if g1.get("closure_ready"):
        print("  closure_ready: true — 可更新 gap register 标 OT2 观测完成")
warn = int(summary.get("warn") or 0)
sys.exit(1 if warn else 0)
PY
