#!/usr/bin/env bash
# Real LingWen1 dev delegate drill — isolated workspace, full delegate_task pipeline.
#
# Usage:
#   bash scripts/butler-lingwen1-delegate-drill.sh
#   bash scripts/butler-lingwen1-delegate-drill.sh --force-workspace
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES="${BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES:-1}"
export BUTLER_EVAL_LLM_BENCHMARK=1

FORCE_WS=0
if [[ "${1:-}" == "--force-workspace" ]]; then
  FORCE_WS=1
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<PY
import json

from butler.ops.lingwen1_delegate_drill import run_lingwen1_delegate_drill

out = run_lingwen1_delegate_drill(live=True, force_workspace=bool(${FORCE_WS}))
print(json.dumps(out, ensure_ascii=False, indent=2))
if not out.get("ok"):
    raise SystemExit(1)
PY
