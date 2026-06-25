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
echo "Next: pip install 'markitdown-mcp' or ensure uvx can fetch it; then bash scripts/butler-extension-ext5-preflight.sh"
