#!/usr/bin/env bash
# LingWen1 real-workspace delegate samples (2–3 production-shaped tasks).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_EVAL_LLM_BENCHMARK=1
export BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES="${BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES:-1}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<'PY'
import json
import sys

from butler.ops.lingwen1_prod_sample import run_lingwen1_prod_samples

out = run_lingwen1_prod_samples(live=True)
print(json.dumps(out, ensure_ascii=False, indent=2))
print()
print(f"LingWen1 prod samples: {out.get('passed')}/{out.get('total')}")
if out.get("passed", 0) < out.get("total", 0):
    sys.exit(1)
PY
