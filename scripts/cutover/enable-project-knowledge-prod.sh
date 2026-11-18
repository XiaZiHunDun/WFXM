#!/usr/bin/env bash
# Enable Project Knowledge inject + sources watch in ~/.config/env (idempotent).
set -euo pipefail

ENV_FILE="${HOME}/.config/env"
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"

set_kv() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >>"$ENV_FILE"
  fi
}

set_kv BUTLER_V5_PROJECT_KNOWLEDGE 1
set_kv BUTLER_V5_PROJECT_KNOWLEDGE_WATCH 1
set_kv BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH config/project-knowledge-sources.json
set_kv BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP 'wechat:WFXM,LingWen1:LingWen,灵文1号:LingWen'

echo "Updated ${ENV_FILE}:"
grep 'BUTLER_V5_PROJECT_KNOWLEDGE' "$ENV_FILE" || true
echo "Restart gateway: systemctl --user restart butler-v5-gateway.service"
