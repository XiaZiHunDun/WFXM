#!/usr/bin/env bash
# B9 release gate — fast oracle Tier-1 (no LLM). Use in pre-release smoke.
#
# Usage:
#   bash scripts/butler-b9-release-gate.sh
#   bash scripts/butler-b9-release-gate.sh --with-stuck
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

WITH_STUCK=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-stuck) WITH_STUCK=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--with-stuck]"
      echo "  Oracle-verify Tier-1 B9 tasks (fast, no API). Exit 1 on failure."
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

python3 - <<PY
import sys
import tempfile
from pathlib import Path

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS
from butler.dev_engine.b9_tiers import B9_STUCK_TASK_IDS, filter_tier_tasks
from butler.dev_engine.llm_delegate_benchmark import B9Mode, run_b9_task

tasks = filter_tier_tasks(B9_LIVE_FIXED_TASKS, tier=1)
if not int("$WITH_STUCK"):
    tasks = [t for t in tasks if t.task_id not in B9_STUCK_TASK_IDS]

failed = []
with tempfile.TemporaryDirectory(prefix="b9_release_gate_") as td:
    base = Path(td)
    for spec in tasks:
        ws = base / spec.task_id
        ws.mkdir(parents=True, exist_ok=True)
        result = run_b9_task(spec, ws, mode=B9Mode.ORACLE)
        if not result.passed:
            failed.append((spec.task_id, result.failure_reasons))

print(f"B9 release gate (oracle tier1): {len(tasks) - len(failed)}/{len(tasks)} passed")
for tid, reasons in failed:
    print(f"  FAIL {tid}: {'; '.join(reasons)}", file=sys.stderr)

if failed:
    sys.exit(1)
PY
