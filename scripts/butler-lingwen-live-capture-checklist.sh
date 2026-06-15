#!/usr/bin/env bash
# LingWen1 production proof checklist — live delegate capture + L3 memory (read-only).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<'PY'
import json
import os
from pathlib import Path

from butler.config import get_butler_home
from butler.memory.memory_scope import project_coding_experiences_path
from butler.ops.b9_prod_weekly import (
    compare_production_delegate_delta,
    summarize_production_delegate_quality,
)
from butler.ops.boundary_observability import g1_04_observation_window_status
from butler.ops.experience_selection_telemetry import forward_selection_precision
from butler.ops.prod_experience_effectiveness import format_prod_experience_effectiveness
from butler.ops.lingwen1_delegate_drill import LINGWEN_PROJECT_NAME
from butler.project.manager import get_project_manager

print("=== LingWen1 live capture checklist ===")
print()

capture = os.getenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "").strip()
print(f"1. BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES={capture or '(unset)'}")
if capture not in ("1", "true", "yes", "on"):
    print("   ACTION: set BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES=1 in .env for live failures → audit")

pm = get_project_manager()
proj = pm.get_project(LINGWEN_PROJECT_NAME)
ws = getattr(proj, "workspace", None) if proj else None
print(f"2. project={LINGWEN_PROJECT_NAME} workspace={ws or 'MISSING'}")
if not ws or not Path(ws).is_dir():
    print("   ACTION: register LingWen1 project workspace in projects registry")

audit = get_butler_home() / "audit" / "delegate_failures.jsonl"
pipeline = 0
lingwen = 0
if audit.is_file():
    for line in audit.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(rec.get("capture_source") or "") != "delegate_pipeline":
            continue
        pipeline += 1
        if str(rec.get("project") or "") in (LINGWEN_PROJECT_NAME, "LingWen1", "灵文1号"):
            lingwen += 1
print(f"3. audit delegate_pipeline rows: total={pipeline} lingwen={lingwen}")

l3_path = project_coding_experiences_path(Path(ws)) if ws else None
prod_fail = 0
if l3_path and l3_path.is_file():
    rows = json.loads(l3_path.read_text(encoding="utf-8"))
    prod_fail = sum(1 for r in rows if str(r.get("id", "")).startswith("PROD_FAIL_"))
print(f"4. L3 coding_experiences PROD_FAIL_*: {prod_fail} path={l3_path or 'n/a'}")

clean = summarize_production_delegate_quality(clean=True)
delta = compare_production_delegate_delta(clean=True)
print(
    f"5. prod_clean failures={clean.get('production_failures_total')} "
    f"snapshots={delta.get('snapshots', 0)} "
    f"verify_fail_delta={delta.get('verify_fail_rate_delta', 'n/a')}"
)

fwd = forward_selection_precision()
print(
    f"6. experience_selection_forward precision={fwd.get('precision')} "
    f"aligned={fwd.get('aligned')}/{fwd.get('scored')}"
)

g1 = g1_04_observation_window_status()
print(
    f"7. G1-04 window feedback={g1.get('feedback_in_window')} "
    f"remaining={g1.get('days_remaining')}d closure_ready={g1.get('closure_ready')}"
)

print()
print(format_prod_experience_effectiveness())

print()
print("=== Weekly rhythm (ops proof) ===")
print("  Sun: bash scripts/butler-b9-weekly-learning.sh")
print("  Mid: bash scripts/butler-prod-delta-observe.sh")
print("  Ad-hoc: bash scripts/butler-lingwen1-prod-sample.sh  # real workspace smoke")
print()
print("Gate metrics: forward>=0.95 | prod_delta_clean trend | lingwen prod sample 3/3")
print("Stretch (non-blocking): Promoted LIVE B9L_prod_lingwen_validate_progress")
PY
