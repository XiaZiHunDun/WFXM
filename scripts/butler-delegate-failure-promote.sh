#!/usr/bin/env bash
# Promote a production delegate failure into the B9 implementation queue.
#
# Usage:
#   bash scripts/butler-delegate-failure-promote.sh              # latest audit row
#   bash scripts/butler-delegate-failure-promote.sh --index 0
#   bash scripts/butler-delegate-failure-promote.sh --reason verify_fail
#   bash scripts/butler-delegate-failure-promote.sh --bundle     # export review bundle
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

INDEX=-1
REASON=""
BUNDLE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --index) INDEX="${2:-0}"; shift 2 ;;
    --reason) REASON="${2:-}"; shift 2 ;;
    --bundle) BUNDLE=1; shift ;;
    -h|--help)
      cat <<'EOF'
Usage: bash scripts/butler-delegate-failure-promote.sh [OPTIONS]

  (default)   Promote latest delegate_failures.jsonl row → queue + scaffold
  --index N   Promote audit row N (0 = oldest in recent window)
  --reason X  Override failure_reason (verify_fail|patch_wrong|no_test|tool_wrong)
  --bundle    Export candidates.json + queue_summary.json under ~/.butler/audit/b9_promotion/
EOF
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

export PROMOTE_INDEX="$INDEX"
export PROMOTE_REASON="$REASON"
export PROMOTE_BUNDLE="$BUNDLE"

python3 - <<'PY'
import json, os, sys
from butler.ops.delegate_failure_b9_promote import (
    export_promotion_bundle,
    promote_from_audit,
    promotion_queue_summary,
)

if os.environ.get("PROMOTE_BUNDLE", "0") == "1":
    out = export_promotion_bundle()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0)

index = int(os.environ.get("PROMOTE_INDEX", "-1"))
reason = os.environ.get("PROMOTE_REASON", "")
result = promote_from_audit(index=index, annotate_reason=reason)
print(json.dumps({k: v for k, v in result.items() if k != "scaffold"}, ensure_ascii=False, indent=2))
if result.get("scaffold"):
    print()
    print("=== B9 Task scaffold (paste into b9_prod_shaped_tasks.py) ===")
    print(result["scaffold"])

summary = promotion_queue_summary()
print()
print(f"Queue: {summary.get('queue_path')} pending={summary.get('pending', 0)} total={summary.get('total', 0)}")

if not result.get("promoted"):
    print()
    print("No audit rows yet. Modeled templates already in B9 LIVE set:")
    for tid in ("B9L_prod_verify_fail", "B9L_prod_patch_wrong", "B9L_prod_no_test"):
        print(f"  - {tid}")
    sys.exit(0)
PY
