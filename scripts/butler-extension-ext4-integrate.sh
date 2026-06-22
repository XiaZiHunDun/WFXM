#!/usr/bin/env bash
# EXT-4 integrate: pin GitHub OpenAPI spec + append github server to ~/.butler/mcp.yaml
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bash "$ROOT/scripts/butler-github-openapi-spec-install.sh"

MCP_CFG="${BUTLER_MCP_CONFIG:-$HOME/.butler/mcp.yaml}"
SPEC_PATH="$HOME/.butler/openapi/github-readonly.yml"

if [[ -f "$MCP_CFG" ]] && grep -qE '^[[:space:]]*github:' "$MCP_CFG" 2>/dev/null; then
  echo "github server already present in $MCP_CFG — skip append"
  exit 0
fi

if [[ ! -f "$MCP_CFG" ]]; then
  cat >"$MCP_CFG" <<'YAML'
version: 1
servers:
YAML
  echo "Created $MCP_CFG"
fi

# Append github block (YAML merge by append — user edits ordering manually if needed)
cat >>"$MCP_CFG" <<YAML

  github:
    transport: stdio
    command: npx
    args:
      - "-y"
      - "@ivotoby/openapi-mcp-server"
      - "--api-base-url"
      - "https://api.github.com"
      - "--openapi-spec"
      - "${SPEC_PATH}"
    timeout_seconds: 90
    env:
      API_HEADERS: "Authorization:Bearer \${GITHUB_TOKEN},Accept:application/vnd.github+json,X-GitHub-Api-Version:2022-11-28"
    tools:
      allow:
        - get-authenticated-usr
        - lst-repos-authenticated-usr
        - get-repo
        - lst-repo-issues
    classify:
      get-authenticated-usr: readonly
      lst-repos-authenticated-usr: readonly
      get-repo: readonly
      lst-repo-issues: readonly
YAML

echo "Appended github server to $MCP_CFG"
echo "Next: set GITHUB_TOKEN in ~/.butler/secrets.yaml or .env, then bash scripts/butler-extension-ext4-preflight.sh"
