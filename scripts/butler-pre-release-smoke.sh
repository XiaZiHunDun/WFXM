#!/usr/bin/env bash
# Pre–manual-test gate: preflight + pytest (default) + project smoke scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROJECT="${1:-灵文1号}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "== 1/7 gateway preflight =="
bash scripts/butler-gateway-ops.sh preflight

echo ""
echo "== 2/7 pytest (exclude live_llm) =="
python3 -m pytest -q --tb=line

echo ""
echo "== 3/7 wechat memory smoke =="
bash scripts/butler-wechat-memory-smoke.sh

echo ""
echo "== 4/7 wechat gateway smoke =="
bash scripts/butler-wechat-gateway-smoke.sh

echo ""
echo "== 5/7 inbound media smoke =="
bash scripts/butler-inbound-media-smoke.sh

echo ""
echo "== 6/7 runtime smoke ($PROJECT, no WeChat push) =="
BUTLER_RUNTIME_PUSH=0 bash scripts/butler-runtime-smoke.sh "$PROJECT"

echo ""
echo "== 7/7 dev delegate smoke =="
bash scripts/butler-dev-delegate-smoke.sh

echo ""
echo "Pre-release smoke: ALL PASSED"
echo "Next: bash scripts/butler-gateway-ops.sh restart"
echo "Then: docs/guides/wechat-daily-smoke-checklist.md (真机)"
