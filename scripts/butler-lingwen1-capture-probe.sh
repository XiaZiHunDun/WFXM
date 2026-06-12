#!/usr/bin/env bash
# Exercise LingWen1 production delegate failure capture (audit + optional LangFuse).
#
# Usage:
#   bash scripts/butler-lingwen1-capture-probe.sh
#   bash scripts/butler-lingwen1-capture-probe.sh --force
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<PY
import json

from butler.ops.lingwen1_capture_probe import run_lingwen1_capture_probe

out = run_lingwen1_capture_probe(force=bool(${FORCE}))
print(json.dumps(out, ensure_ascii=False, indent=2))
PY
