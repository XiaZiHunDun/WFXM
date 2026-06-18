#!/usr/bin/env bash
# EXT-1 preflight: Firecrawl MCP readiness (no API call required).
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

echo "EXT-1 Firecrawl MCP preflight"

if command -v node >/dev/null 2>&1; then
  node_ver="$(node --version 2>/dev/null | sed 's/^v//' || echo '0')"
  node_major="${node_ver%%.*}"
  if [[ "${node_major:-0}" -ge 18 ]]; then
    _pass "node: $(command -v node) (v${node_ver})"
  else
    _warn "node v${node_ver} < 18 (Firecrawl MCP requires Node 18+)"
  fi
else
  _fail "node not in PATH (Firecrawl MCP requires Node 18+)"
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
  *) _warn "BUTLER_MCP_STDIO_ALLOW_COMMANDS lacks npx (needed for firecrawl-mcp)" ;;
esac

if [[ -n "${FIRECRAWL_API_KEY:-}" ]]; then
  _pass "FIRECRAWL_API_KEY set (len=${#FIRECRAWL_API_KEY})"
else
  _warn "FIRECRAWL_API_KEY unset — add to secrets.yaml or .env before live scrape"
fi

for cfg in "$HOME/.butler/mcp.yaml" "$ROOT/.butler/mcp.yaml"; do
  if [[ -f "$cfg" ]] && grep -q 'firecrawl' "$cfg" 2>/dev/null; then
    _pass "firecrawl block in $cfg"
    found_firecrawl=1
    break
  fi
done
if [[ "${found_firecrawl:-0}" -eq 0 ]]; then
  _warn "no firecrawl server in ~/.butler/mcp.yaml or project .butler/mcp.yaml"
fi

echo ""
echo "summary: ok=$ok warn=$warn fail=$fail"
if [[ "$fail" -gt 0 ]]; then
  echo "See docs/plans/active/extension-candidates/ext-1-web-scrape-mcp-2026-06.md §6"
  exit 1
fi
exit 0
