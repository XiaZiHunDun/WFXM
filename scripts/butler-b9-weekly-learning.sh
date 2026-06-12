#!/usr/bin/env bash
# B9 weekly learning loop — export, Tier-1 LIVE gate, Tier-2 probe, SWE subset, lessons.
#
# Usage:
#   bash scripts/butler-b9-weekly-learning.sh
#   bash scripts/butler-b9-weekly-learning.sh minimax/MiniMax-M3
# Cron example (weekly Sunday 03:00):
#   0 3 * * 0 cd /path/to/WFXM && bash scripts/butler-b9-weekly-learning.sh >> /tmp/b9-weekly.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_EVAL_LLM_BENCHMARK=1

MODEL="${1:-minimax/MiniMax-M3}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

echo "=== B9 weekly: export Tier-1 curriculum ==="
bash "$ROOT/scripts/butler-b9-export-curriculum.sh" --tier1-only

echo ""
echo "=== B9 weekly: Tier-1 LIVE model=$MODEL ==="
bash "$ROOT/scripts/butler-eval-b9-probe-model.sh" --tier1 "$MODEL"

echo ""
echo "=== B9 weekly: Tier-2 probe (stretch, non-blocking) ==="
bash "$ROOT/scripts/butler-eval-b9-probe-model.sh" "$MODEL" || echo "(tier2 probe had failures — stretch only)"

echo ""
echo "=== B9 weekly: SWE-bench subset (non-blocking) ==="
bash "$ROOT/scripts/butler-eval-swebench-live.sh" || echo "(SWE weekly subset had failures)"

echo ""
echo "=== B9 weekly: lesson summary ==="
python3 - <<'PY'
import json
from collections import Counter
from pathlib import Path

from butler.ops.b9_lessons import b9_lessons_path

p = b9_lessons_path()
if not p.is_file():
    print("(no lessons yet)")
    raise SystemExit(0)
rows = []
for line in p.read_text(encoding="utf-8").splitlines():
    if line.strip():
        rows.append(json.loads(line))
kinds = Counter(r.get("kind") for r in rows)
classes = Counter(r.get("classification") for r in rows)
print(f"lessons_total={len(rows)} kinds={dict(kinds)} classifications={dict(classes)}")
print(f"path={p}")

from butler.ops.b9_harness_audit import (
    format_harness_friction_delta,
    format_harness_friction_report,
    record_harness_friction_snapshot,
)

print()
snap = record_harness_friction_snapshot()
print(format_harness_friction_report(snap))
print(format_harness_friction_delta(snap.get("delta")))
PY
