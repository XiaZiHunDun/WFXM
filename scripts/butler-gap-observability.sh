#!/usr/bin/env bash
# G1/G2 honest-boundary observability gate (read-only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<'PY'
import json
import sys

from butler.ops.boundary_observability import (
    boundary_observability_summary,
    collect_boundary_observations,
)

obs = collect_boundary_observations()
summary = boundary_observability_summary()
print("=== G1/G2 boundary observability ===")
for o in obs:
    print(o.line(verbose=True))
print()
print(json.dumps(summary, ensure_ascii=False, indent=2))
warn = int(summary.get("warn") or 0)
sys.exit(1 if warn else 0)
PY
