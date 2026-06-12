#!/usr/bin/env bash
# B9 weekly learning loop — export curriculum, run Tier-1 LIVE, summarize lessons.
#
# Usage:
#   bash scripts/butler-b9-weekly-learning.sh
#   bash scripts/butler-b9-weekly-learning.sh minimax/MiniMax-M3
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
PY
