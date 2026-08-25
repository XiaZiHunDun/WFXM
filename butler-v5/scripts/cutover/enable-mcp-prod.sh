#!/usr/bin/env bash
# Enable multi-server MCP + WeChat tool allowlist in ~/.config/butler-v5/env (idempotent).
# Does NOT write API keys — set FIRECRAWL_API_KEY, GITHUB_PERSONAL_ACCESS_TOKEN,
# TODOIST_API_TOKEN, API_HEADERS in env separately.
set -euo pipefail

ENV_FILE="${HOME}/.config/butler-v5/env"
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

set_kv BUTLER_V5_MCP_ENABLED 1
set_kv BUTLER_V5_MCP_MANIFEST_PATH config/mcp-manifest.json
set_kv BUTLER_V5_MCP_TIMEOUT_MS 120000
set_kv BUTLER_V5_MCP_REQUIRE_CONSENT 1
set_kv BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH config/wechat-tool-allowlist.json

if grep -q '^BUTLER_V5_MCP_COMMAND=' "$ENV_FILE" 2>/dev/null; then
  echo "WARN: remove BUTLER_V5_MCP_COMMAND from ${ENV_FILE} (overrides manifest)"
fi
if grep -q '^BUTLER_V5_MCP_SERVER_ID=' "$ENV_FILE" 2>/dev/null; then
  echo "WARN: remove BUTLER_V5_MCP_SERVER_ID from ${ENV_FILE} (overrides manifest)"
fi

echo "Updated ${ENV_FILE}:"
grep -E 'BUTLER_V5_MCP_|BUTLER_V5_WECHAT_TOOL_ALLOWLIST' "$ENV_FILE" || true
echo "Restart gateway: systemctl --user restart butler-v5-gateway.service"
