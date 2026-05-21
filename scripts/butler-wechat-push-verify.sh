#!/usr/bin/env bash
# WeChat runtime push verification (spaced sends to avoid iLink rate limit).
# Owner should confirm messages arrive on WeChat within ~2 minutes of script end.
set -uo pipefail
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
export BUTLER_RUNTIME_ENABLED=1
export BUTLER_RUNTIME_PUSH=1
# Spacing between runtime pushes (notify.py also enforces this)
export BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS="${BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS:-25}"
export WECHAT_SEND_CHUNK_RETRIES="${WECHAT_SEND_CHUNK_RETRIES:-6}"
export WECHAT_SEND_CHUNK_RETRY_DELAY_SECONDS="${WECHAT_SEND_CHUNK_RETRY_DELAY_SECONDS:-2}"

echo "== WeChat push verify (project=$PROJECT) =="
echo "Cooldown: ${BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS}s | chunk retries: ${WECHAT_SEND_CHUNK_RETRIES}"
PRE_WAIT="${BUTLER_WECHAT_PUSH_PRE_WAIT_SECONDS:-60}"
if [[ "$PRE_WAIT" != "0" ]]; then
  echo "Waiting ${PRE_WAIT}s for iLink rate-limit window to cool down..."
  sleep "$PRE_WAIT"
fi
PING_OK=0
if python3 -c "
from butler.runtime.notify import push_runtime_message, resolve_owner_wechat_chat_id
import os
cid = resolve_owner_wechat_chat_id()
if not cid:
    raise SystemExit('No BUTLER_OWNER_WECHAT_ID / WECHAT_ALLOWED_USERS')
if not os.getenv('WECHAT_TOKEN','').strip():
    raise SystemExit('WECHAT_TOKEN missing')
ok = push_runtime_message(
    '[Butler] 推送验证 1/2',
    '这是一条短消息，用于验证 runtime 微信推送与限流退避。若收到请忽略。',
)
print('ping push:', 'ok' if ok else 'FAILED')
raise SystemExit(0 if ok else 1)
"; then
  PING_OK=1
else
  echo "WARN: ping push failed (rate limit?); continuing to factory-status-daily..."
fi

echo ""
echo "== cooldown before second push =="
sleep "${BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS}"
echo ""
echo "== runtime job with push (factory-status-daily) =="
python3 -m butler.main runtime run factory-status-daily --project "$PROJECT"

echo ""
echo "== WeChat push verify done =="
echo "请在微信确认收到："
if [[ "$PING_OK" == "1" ]]; then
  echo "  1) [Butler] 推送验证 1/2"
else
  echo "  1) [Butler] 推送验证 1/2 — 未成功（可忽略，看第 2 条）"
fi
echo "  2) factory-status-daily 摘要（含 phase/step）"
echo "若均未收到：等 15–30 分钟后重跑，或微信发 /运行 factory-status-daily"
