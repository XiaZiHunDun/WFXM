#!/usr/bin/env bash
# End-to-end demo: seed audit → promote → bundle (pipeline smoke).
#
# Usage:
#   bash scripts/butler-delegate-failure-promote-demo.sh
#   bash scripts/butler-delegate-failure-promote-demo.sh --force   # re-seed even if audit non-empty
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

FORCE=0
export PROMOTE_DEMO_FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; PROMOTE_DEMO_FORCE=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--force]"
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
done

python3 - <<PY
import json, os, sys
from butler.ops.delegate_failure_b9_promote import run_promotion_demo

force = os.environ.get("PROMOTE_DEMO_FORCE", "0") == "1"
result = run_promotion_demo(force_seed=force)

print("=== B9 promotion demo ===")
print(json.dumps({
    "seed": result["seed"],
    "promote": result["promote"],
    "bundle": result["bundle"],
    "queue_pending": result["queue_pending"],
}, ensure_ascii=False, indent=2))

if result.get("scaffold"):
    print()
    print("=== Scaffold (from promoted demo row) ===")
    print(result["scaffold"])

if not result["promote"].get("promoted"):
    print("Promote step did not run; check seed result.", file=sys.stderr)
    sys.exit(1)

print()
print("DEMO OK: audit seeded → promoted → bundle exported")
PY
