#!/usr/bin/env bash
# Export B9 oracle curriculum + seed coding_experiences (Phase 1 learning loop).
#
# Usage:
#   bash scripts/butler-b9-export-curriculum.sh
#   bash scripts/butler-b9-export-curriculum.sh --tier1-only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

TIER1_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier1-only) TIER1_ONLY=1 ;;
    -h|--help)
      echo "Usage: $0 [--tier1-only]"
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
  shift
done

python3 - <<PY
import json, sys

from butler.dev_engine.b9_oracle_curriculum import B9_ORACLE_EPISODES
from butler.dev_engine.b9_tiers import b9_task_tier
from butler.ops.b9_lessons import export_curriculum_and_seed_experiences

task_ids = None
if int($TIER1_ONLY):
    task_ids = [tid for tid in B9_ORACLE_EPISODES if b9_task_tier(tid) == 1]

summary = export_curriculum_and_seed_experiences(task_ids=task_ids)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
