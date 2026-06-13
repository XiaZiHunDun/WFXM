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
echo "=== B9 weekly: Tier-2 probe (conditional gate) ==="
TIER2_GATE_ENABLED="${BUTLER_B9_TIER2_GATE_ENABLED:-1}"
TIER2_MIN="${BUTLER_B9_TIER2_GATE_MIN_PASSED:-2}"
if bash "$ROOT/scripts/butler-eval-b9-probe-model.sh" "$MODEL"; then
  echo "Tier-2 probe: gate passed (enabled=${TIER2_GATE_ENABLED}, min=${TIER2_MIN})"
else
  if [[ "$TIER2_GATE_ENABLED" == "1" ]]; then
    echo "B9 TIER2 PROBE GATE: FAILED (need >=${TIER2_MIN}/3)" >&2
    exit 1
  fi
  echo "(tier2 probe had failures — stretch only; BUTLER_B9_TIER2_GATE_ENABLED=0)"
fi

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
    backfill_selection_task_affinity,
    summarize_experience_lifecycle,
    summarize_experience_selections,
    summarize_selection_precision,
    replay_selection_precision,
    forward_selection_precision,
)

print("lingwen1_seed=", seed_lingwen1_failure_audit())
print("lingwen1_capture_probe=", run_lingwen1_capture_probe())
print(f"lingwen1_note={LINGWEN1_CAPTURE_NOTE}")
bf = backfill_selection_task_affinity(dry_run=False)
print(f"experience_affinity_backfill={bf}")
print("experience_selections=", summarize_experience_selections())
print("experience_selection_precision=", summarize_selection_precision())
print("experience_selection_replay=", replay_selection_precision())
print("experience_selection_forward=", forward_selection_precision())
print("experience_lifecycle=", summarize_experience_lifecycle())
PY

echo ""
echo "=== B9 weekly: promoted prod LIVE probe (phase C, non-blocking) ==="
PROMOTED_RC=0
python3 - <<'PY' || PROMOTED_RC=$?
import json, sys
from butler.ops.b9_prod_weekly import run_promoted_prod_live_probe

probe = run_promoted_prod_live_probe()
layers = probe.get("layers") or {}
core = layers.get("core") or {}
stretch = layers.get("stretch") or {}
print(json.dumps(probe, ensure_ascii=False, indent=2))
print(
    f"\nPromoted prod core ({probe.get('mode')}): "
    f"{core.get('passed', probe.get('passed'))}/{core.get('total', probe.get('total'))}"
)
if stretch.get("total"):
    print(f"Promoted prod stretch ({probe.get('mode')}): {stretch.get('passed')}/{stretch.get('total')}")
if not probe.get("core_gate_ok", True):
    print("PROMOTED PROD CORE: had failures", file=sys.stderr)
    raise SystemExit(1)
if stretch.get("total") and stretch.get("passed", 0) < stretch.get("total", 0):
    print("PROMOTED PROD STRETCH: had failures (non-blocking)", file=sys.stderr)
PY
if [ "${PROMOTED_RC:-0}" -ne 0 ]; then
  echo "(promoted prod core probe had failures — see stderr)"
fi

echo ""
echo "=== B9 weekly: LingWen1 prod sample (phase C, non-blocking) ==="
bash "$ROOT/scripts/butler-lingwen1-prod-sample.sh" 2>&1 || echo "(lingwen prod sample had failures — stretch only)"

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
