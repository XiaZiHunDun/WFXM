#!/usr/bin/env bash
# Pre–manual-test gate: preflight + pytest (default) + project smoke scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# 灵文 runtime 与 DemoPilot 分步冒烟；$1 保留兼容但不再覆盖灵文 runtime 步骤
RUNTIME_PROJECT="灵文1号"

if [[ -f .env ]]; then
  set -a
  set +u
  # shellcheck disable=SC1091
  source .env
  set -u
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "== 1/9 gateway preflight =="
bash scripts/butler-gateway-ops.sh preflight

echo ""
echo "== 2/9 pytest (exclude live_llm) =="
python3 -m pytest -q --tb=line

echo ""
echo "== 3/9 wechat memory smoke =="
bash scripts/butler-wechat-memory-smoke.sh

echo ""
echo "== 4/9 wechat gateway smoke =="
bash scripts/butler-wechat-gateway-smoke.sh

echo ""
echo "== 5/9 inbound media smoke =="
bash scripts/butler-inbound-media-smoke.sh

echo ""
echo "== 6/9 runtime smoke ($RUNTIME_PROJECT, default no push) =="
bash scripts/butler-runtime-smoke.sh "$RUNTIME_PROJECT"

echo ""
echo "== 7/9 lingwen lead smoke =="
bash scripts/butler-lingwen-lead-smoke.sh

echo ""
echo "== 8/9 dev delegate smoke =="
bash scripts/butler-dev-delegate-smoke.sh

echo ""
echo "== 9/9 DemoPilot project smoke =="
bash scripts/butler-demo-pilot-smoke.sh

echo ""
echo "Pre-release smoke: ALL PASSED"
echo "Next: bash scripts/butler-gateway-ops.sh restart"
echo "Then: docs/guides/wechat-daily-smoke-checklist.md (真机)"
