#!/usr/bin/env bash
# EXT-5 integrate: append markitdown MCP server to ~/.butler/mcp.yaml
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MCP_CFG="${BUTLER_MCP_CONFIG:-$HOME/.butler/mcp.yaml}"

if [[ -f "$MCP_CFG" ]] && grep -qE '^[[:space:]]*markitdown:' "$MCP_CFG" 2>/dev/null; then
  echo "markitdown server already present in $MCP_CFG — skip append"
  exit 0
fi

if [[ ! -f "$MCP_CFG" ]]; then
  cat >"$MCP_CFG" <<'YAML'
version: 1
servers:
YAML
  echo "Created $MCP_CFG"
fi

cat >>"$MCP_CFG" <<'YAML'

  markitdown:
    transport: stdio
    command: uvx
    args:
      - "markitdown-mcp"
    timeout_seconds: 120
    tools:
      allow:
        - convert_to_markdown
    classify:
      convert_to_markdown: readonly
YAML

echo "Appended markitdown server to $MCP_CFG"
echo "Next:"
echo "  1. Add to .env: BUTLER_MCP_MAX_SERVERS=4  (4 MCP servers; default 3 drops markitdown)"
echo "  2. pip install markitdown-mcp  OR  ensure uvx can fetch it"
echo "  3. bash scripts/butler-extension-ext5-preflight.sh"
echo "  4. systemctl --user restart butler-gateway.service  (or butler-gateway-ops.sh restart)"
echo "  5. docs/guides/ext5-wechat-verify-2026-06.md"
