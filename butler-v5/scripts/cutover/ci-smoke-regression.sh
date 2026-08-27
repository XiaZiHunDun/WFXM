#!/usr/bin/env bash
# CI / local: start v5 gateway (pglite) and run loopback smoke:regression:quick.
# No real WeChat device or iLink token required.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WFXM_ROOT="$(cd "${ROOT}/.." && pwd)"
cd "$ROOT"

export NODE_ENV=test
export PORT="${PORT:-3010}"
export BUTLER_V5_WORKSPACE_ROOT="${WFXM_ROOT}"
export BUTLER_V5_SUBAGENT_ENABLED=1
export BUTLER_V5_RUN_NOTIFY_ENABLED=1
export BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX=/tmp/butler-v5-ci-notify.jsonl
export BUTLER_V5_LLM_FIXTURE_DIR="${ROOT}/config/llm-fixtures/wechat"
export BUTLER_V5_INTAKE_LLM=0
export BUTLER_V5_DEV_VERIFY_ENABLED=1
export BUTLER_V5_DEV_VERIFY_CMD='["echo","ok"]'
export WS_PORT=3011
export BUTLER_V5_SUBAGENT_WORKER_INTERVAL_MS=500
export BUTLER_V5_TASK_RUN_ASYNC=1
export BUTLER_V5_PROJECT_KNOWLEDGE=1
export BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP='wechat:WFXM,LingWen1:LingWen,灵文1号:LingWen'
export BUTLER_V5_MCP_ENABLED=1
export BUTLER_V5_MCP_TOOL_NAMES=search
export BUTLER_V5_TRACE=0

API="http://127.0.0.1:${PORT}"

cleanup() {
  if [[ -n "${GATEWAY_PID:-}" ]] && kill -0 "$GATEWAY_PID" 2>/dev/null; then
    kill "$GATEWAY_PID" 2>/dev/null || true
    wait "$GATEWAY_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Avoid stale gateway on CI port (production may use :3000).
fuser -k "${PORT}/tcp" "${WS_PORT}/tcp" 2>/dev/null || true
sleep 1

echo "ci-smoke: starting gateway on ${API} (NODE_ENV=test, pglite)"
pnpm exec tsx cli/src/index.ts start &
GATEWAY_PID=$!

for i in $(seq 1 45); do
  if curl -sf "${API}/healthz" >/dev/null 2>&1; then
    echo "ci-smoke: healthz ok (${i}s)"
    break
  fi
  if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
    echo "ci-smoke FAIL: gateway exited before healthz"
    exit 1
  fi
  sleep 1
done

if ! curl -sf "${API}/healthz" >/dev/null 2>&1; then
  echo "ci-smoke FAIL: healthz timeout"
  exit 1
fi

echo "ci-smoke: running smoke:regression --quick --skip=notify"
node scripts/cutover/smoke-regression.mjs --quick --skip=notify --api="${API}"
echo "ci-smoke PASS"
