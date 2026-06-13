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

echo ""
echo "=== B9 weekly: production delegate quality snapshot ==="
python3 - <<'PY'
from butler.dev_engine.b9_experience_retrieval import backfill_b9_experience_retrieval
from butler.ops.b9_prod_weekly import (
    format_production_delegate_delta,
    format_production_delegate_report,
    record_production_delegate_snapshot,
)

backfill = backfill_b9_experience_retrieval()
snap = record_production_delegate_snapshot()
print(format_production_delegate_report(snap))
print(format_production_delegate_delta(snap.get("delta")))
clean = snap.get("clean") or {}
print(format_production_delegate_report(clean, clean=True))
print(format_production_delegate_delta(snap.get("clean_delta"), clean=True))
print(f"b9_experience_backfill_updated={backfill.get('updated', 0)}")
from butler.ops.lingwen1_capture_probe import run_lingwen1_capture_probe
from butler.ops.lingwen1_failure_seed import seed_lingwen1_failure_audit
from butler.ops.b9_prod_promoted_registry import LINGWEN1_CAPTURE_NOTE
from butler.ops.experience_selection_telemetry import (
    summarize_experience_lifecycle,
    summarize_experience_selections,
)

print("lingwen1_seed=", seed_lingwen1_failure_audit())
print("lingwen1_capture_probe=", run_lingwen1_capture_probe())
print(f"lingwen1_note={LINGWEN1_CAPTURE_NOTE}")
print("experience_selections=", summarize_experience_selections())
print("experience_lifecycle=", summarize_experience_lifecycle())
PY

echo ""
echo "=== B9 weekly: promoted prod LIVE probe (phase C, non-blocking) ==="
python3 - <<'PY'
import json, sys
from butler.ops.b9_prod_weekly import run_promoted_prod_live_probe

probe = run_promoted_prod_live_probe()
print(json.dumps(probe, ensure_ascii=False, indent=2))
print(f"\nPromoted prod ({probe.get('mode')}): {probe.get('passed')}/{probe.get('total')}")
if probe.get("passed", 0) < probe.get("total", 0):
    print("PROMOTED PROD BENCHMARK: had failures", file=sys.stderr)
    raise SystemExit(1)
PY
if [ $? -ne 0 ]; then echo "(promoted prod probe had failures — stretch only)"; fi

echo ""
echo "=== B9 weekly: promotion queue sync + bundle ==="
python3 - <<'PY'
import json

from butler.ops.b9_prod_weekly import promote_latest_production_failure
from butler.ops.delegate_failure_b9_promote import (
    dismiss_spurious_promotion_queue_items,
    export_promotion_bundle,
    promotion_queue_summary,
    sync_promotion_queue_with_tasks,
)

dismissed = dismiss_spurious_promotion_queue_items()
synced = sync_promotion_queue_with_tasks()
promote = promote_latest_production_failure()
bundle = export_promotion_bundle(audit_limit=20)
summary = promotion_queue_summary()
print(
    json.dumps(
        {
            "promotion_dismissed": dismissed.get("dismissed", 0),
            "promotion_synced": synced.get("synced", 0),
            "production_promoted": promote.get("promoted", False),
            "production_promote_reason": promote.get("reason", ""),
            "queue_pending": summary.get("pending", 0),
            "candidates_path": bundle.get("candidates_path"),
            "queue_summary_path": bundle.get("queue_summary_path"),
        },
        ensure_ascii=False,
        indent=2,
    )
)
PY
