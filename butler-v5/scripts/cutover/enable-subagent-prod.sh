#!/usr/bin/env bash
# Enable subagent + proactive run notify in ~/.config/butler-v5/env (idempotent).
#
# Default: real iLink push (BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX removed).
# Loopback acceptance: bash enable-subagent-prod.sh --mock-outbox
set -euo pipefail

ENV_FILE="${HOME}/.config/butler-v5/env"
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"

MOCK_OUTBOX=""
if [[ "${1:-}" == "--mock-outbox" ]]; then
  MOCK_OUTBOX="/tmp/butler-v5-notify-acceptance.jsonl"
fi

set_kv() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >>"$ENV_FILE"
  fi
}

set_kv BUTLER_V5_SUBAGENT_ENABLED 1
set_kv BUTLER_V5_RUN_NOTIFY_ENABLED 1
set_kv BUTLER_V5_TASK_RUN_ASYNC 1
set_kv BUTLER_V5_MCP_READONLY_AUTO_ALLOW 1

if [[ -n "$MOCK_OUTBOX" ]]; then
  set_kv BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX "$MOCK_OUTBOX"
  echo "Mode: loopback mock outbox → ${MOCK_OUTBOX}"
else
  sed -i '/^BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX=/d' "$ENV_FILE" 2>/dev/null || true
  echo "Mode: real iLink push (mock outbox removed)"
fi

echo "Updated ${ENV_FILE}:"
grep -E 'BUTLER_V5_SUBAGENT_|BUTLER_V5_RUN_NOTIFY_|BUTLER_V5_TASK_RUN_|BUTLER_V5_MCP_READONLY_' "$ENV_FILE" || true
echo "Restart gateway: systemctl --user restart butler-v5-gateway.service"
