#!/usr/bin/env bash
# EXT-2 preflight: Todoist OpenAPI MCP readiness (no API call required).
set -euo pipefail

ROOT="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"
butler_source_env "$ROOT/.env" 2>/dev/null || true

ok=0
warn=0
fail=0

_pass() { printf '  [ok] %s\n' "$1"; ok=$((ok + 1)); }
_warn() { printf '  [warn] %s\n' "$1"; warn=$((warn + 1)); }
_fail() { printf '  [fail] %s\n' "$1"; fail=$((fail + 1)); }

echo "EXT-2 Todoist OpenAPI MCP preflight"

if command -v node >/dev/null 2>&1; then
  node_ver="$(node --version 2>/dev/null | sed 's/^v//' || echo '0')"
  node_major="${node_ver%%.*}"
  if [[ "${node_major:-0}" -ge 18 ]]; then
    _pass "node: $(command -v node) (v${node_ver})"
  else
    _warn "node v${node_ver} < 18 (@ivotoby/openapi-mcp-server requires Node 18+)"
  fi
else
  _fail "node not in PATH (openapi-mcp-server requires Node 18+)"
fi

if command -v npx >/dev/null 2>&1; then
  _pass "npx: $(command -v npx)"
else
  _fail "npx not in PATH — set BUTLER_MCP_STDIO_ALLOW_COMMANDS or install Node"
fi

if PYTHONPATH="$ROOT" python3 -c "import mcp" 2>/dev/null; then
  _pass "python mcp SDK installed"
else
  _fail "pip install butler-system[mcp] (import mcp failed)"
fi

if [[ "${BUTLER_MCP_ENABLED:-0}" == "1" ]]; then
  _pass "BUTLER_MCP_ENABLED=1"
else
  _warn "BUTLER_MCP_ENABLED not 1 (MCP off until enabled)"
fi

case "${BUTLER_MCP_STDIO_ALLOW_COMMANDS:-python,python3,uvx}" in
  *npx*) _pass "BUTLER_MCP_STDIO_ALLOW_COMMANDS includes npx" ;;
  *) _warn "BUTLER_MCP_STDIO_ALLOW_COMMANDS lacks npx (needed for @ivotoby/openapi-mcp-server)" ;;
esac

if [[ -n "${TODOIST_API_TOKEN:-}" ]]; then
  _pass "TODOIST_API_TOKEN set (len=${#TODOIST_API_TOKEN})"
else
  secrets_token=""
  if [[ -f "${BUTLER_SECRETS_PATH:-$HOME/.butler/secrets.yaml}" ]]; then
    secrets_token="$(python3 - "${BUTLER_SECRETS_PATH:-$HOME/.butler/secrets.yaml}" <<'PY'
import sys
from pathlib import Path
import yaml
path = Path(sys.argv[1])
if not path.is_file():
    sys.exit(0)
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
val = str(data.get("TODOIST_API_TOKEN") or "").strip()
if val:
    print(val)
PY
)"
  fi
  if [[ -n "$secrets_token" ]]; then
    if [[ "${BUTLER_MCP_ENABLED:-0}" == "1" ]]; then
      _fail "TODOIST_API_TOKEN in secrets.yaml but not process env — run: bash scripts/butler-todoist-token-sync.sh"
    else
      _warn "TODOIST_API_TOKEN only in secrets.yaml — sync before MCP live calls"
    fi
  elif [[ "${BUTLER_MCP_ENABLED:-0}" == "1" ]]; then
    _fail "TODOIST_API_TOKEN unset — add to secrets.yaml then bash scripts/butler-todoist-token-sync.sh"
  else
    _warn "TODOIST_API_TOKEN unset — add to secrets.yaml or .env before live calls"
  fi
fi

spec_pin="$HOME/.butler/openapi/todoist-rest-v2.yml"
if [[ -f "$spec_pin" ]]; then
  _pass "pinned OpenAPI spec: $spec_pin"
else
  _warn "no pinned spec at $spec_pin (curl per ext-2 doc §7.1 or use raw URL in mcp.yaml)"
fi

for cfg in "$HOME/.butler/mcp.yaml" "$ROOT/.butler/mcp.yaml"; do
  if [[ -f "$cfg" ]] && grep -q 'todoist' "$cfg" 2>/dev/null; then
    _pass "todoist block in $cfg"
    found_todoist=1
    break
  fi
done
if [[ "${found_todoist:-0}" -eq 0 ]]; then
  _warn "no todoist server in ~/.butler/mcp.yaml or project .butler/mcp.yaml"
fi

echo ""
echo "summary: ok=$ok warn=$warn fail=$fail"
if [[ "$fail" -gt 0 ]]; then
  echo "See docs/plans/active/extension-candidates/ext-2-openapi-http-2026-06.md §7"
  exit 1
fi
exit 0
