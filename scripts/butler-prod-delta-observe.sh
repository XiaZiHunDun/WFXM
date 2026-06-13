#!/usr/bin/env bash
# Production delegate quality snapshot + delta (between weekly B9 runs).
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
import sys

from butler.ops.b9_prod_weekly import (
    compare_production_delegate_delta,
    format_production_delegate_delta,
    format_production_delegate_report,
    record_production_delegate_snapshot,
    summarize_production_delegate_quality,
)

summary = summarize_production_delegate_quality(clean=True)
snap = record_production_delegate_snapshot()
print("=== Production delegate observe (recorded snapshot) ===")
print(format_production_delegate_report(snap))
print(format_production_delegate_delta(snap.get("delta")))
clean = snap.get("clean") or {}
print(format_production_delegate_report(clean, clean=True))
print(format_production_delegate_delta(snap.get("clean_delta"), clean=True))
delta = compare_production_delegate_delta(clean=True)
print(json.dumps({"clean_delta_detail": delta}, ensure_ascii=False, indent=2))
if int(delta.get("snapshots") or 0) < 2:
    print("note: need 2+ clean snapshots for meaningful prod_delta_clean", file=sys.stderr)
PY
