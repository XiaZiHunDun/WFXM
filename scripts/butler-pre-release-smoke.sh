#!/usr/bin/env bash
# Pre–manual-test gate: preflight + pytest (default) + project smoke scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# 灵文 runtime 与 DemoPilot 分步冒烟；$1 保留兼容但不再覆盖灵文 runtime 步骤
RUNTIME_PROJECT="灵文1号"

# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"
if [[ -f .env ]]; then
  butler_source_env "$ROOT/.env"
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "== 1/14 gateway preflight =="
bash scripts/butler-gateway-ops.sh preflight

echo ""
echo "== 1b/14 P3-H recall rollout verify =="
bash scripts/butler-p3h-rollout-verify.sh

echo ""
echo "== 2/14 pytest (exclude live_llm) =="
python3 -m pytest -q --tb=line

echo ""
echo "== 2b/14 builtin tool orthogonality =="
bash scripts/builtin-tool-orthogonality-lint.sh --warn-only
python3 -m pytest tests/test_tool_orthogonality_lint.py -q --tb=line

echo ""
echo "== 3/14 wechat memory smoke =="
bash scripts/butler-wechat-memory-smoke.sh

echo ""
echo "== 4/14 wechat gateway smoke =="
bash scripts/butler-wechat-gateway-smoke.sh

echo ""
echo "== 5/14 inbound media smoke =="
bash scripts/butler-inbound-media-smoke.sh

echo ""
echo "== 6/14 runtime smoke ($RUNTIME_PROJECT, default no push) =="
bash scripts/butler-runtime-smoke.sh "$RUNTIME_PROJECT"

echo ""
echo "== 7/14 lingwen lead smoke =="
bash scripts/butler-lingwen-lead-smoke.sh

echo ""
echo "== 8/14 dev delegate smoke =="
bash scripts/butler-dev-delegate-smoke.sh

echo ""
echo "== 9/14 DemoPilot project smoke =="
bash scripts/butler-demo-pilot-smoke.sh

echo ""
echo "== 10/14 B9 oracle Tier-1 release gate =="
bash scripts/butler-b9-release-gate.sh

echo ""
echo "== 11/14 network route policy =="
bash scripts/butler-web-search-route-sim.sh

echo ""
echo "== 12/14 network route strict handler (warn-only) =="
if bash scripts/butler-web-search-route-sim.sh --handler --strict-handler; then
  echo "  strict handler: ok"
else
  echo "  WARN: strict handler failed — review LLM tool routing before prod (daily follow-up uses soft --handler)"
fi

echo ""
echo "== 13/14 wechat owner sim --quick (warn-only) =="
if bash scripts/butler-wechat-owner-sim.sh --quick; then
  echo "  owner sim: ok"
else
  echo "  WARN: owner sim failed — review handler scenarios before prod (needs LLM key)"
fi

echo ""
echo "Pre-release smoke: ALL PASSED"
echo "Next: bash scripts/butler-gateway-ops.sh restart"
echo "Then: docs/guides/wechat-daily-smoke-checklist.md (真机)"
