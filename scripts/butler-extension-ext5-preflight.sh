#!/usr/bin/env bash
# EXT-5 preflight: MarkItDown MCP readiness (no conversion required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

echo "EXT-5 MarkItDown MCP preflight"

manifest="$ROOT/.butler/extensions/markitdown-ingest/manifest.yaml"
if [[ -f "$manifest" ]]; then
  _pass "manifest: .butler/extensions/markitdown-ingest/manifest.yaml"
else
  _fail "missing $manifest"
fi

if command -v uvx >/dev/null 2>&1; then
  _pass "uvx: $(command -v uvx)"
else
  _fail "uvx not in PATH — install uv or add to BUTLER_MCP_STDIO_ALLOW_COMMANDS"
fi

case "${BUTLER_MCP_STDIO_ALLOW_COMMANDS:-python,python3,uvx}" in
  *uvx*) _pass "BUTLER_MCP_STDIO_ALLOW_COMMANDS includes uvx" ;;
  *) _warn "BUTLER_MCP_STDIO_ALLOW_COMMANDS lacks uvx" ;;
esac

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

if [[ "${BUTLER_INGEST_ENABLED:-0}" == "1" ]]; then
  _pass "BUTLER_INGEST_ENABLED=1"
else
  _warn "BUTLER_INGEST_ENABLED not 1 (EXT-3 ingest CLI off; enable for reindex path)"
fi

if python3 -c "from markitdown import MarkItDown" 2>/dev/null; then
  _pass "markitdown python package (documents extra) available"
elif command -v markitdown-mcp >/dev/null 2>&1; then
  _pass "markitdown-mcp CLI on PATH"
else
  _warn "install: pip install markitdown-mcp  OR  pip install -e '.[documents]'"
fi

MCP_CFG="${BUTLER_MCP_CONFIG:-$HOME/.butler/mcp.yaml}"
if [[ -f "$MCP_CFG" ]] && grep -qE '^[[:space:]]*markitdown:' "$MCP_CFG" 2>/dev/null; then
  _pass "mcp.yaml: markitdown server configured"
else
  _warn "no markitdown in $MCP_CFG — run: bash scripts/butler-extension-ext5-integrate.sh"
fi

echo ""
echo "summary: ok=$ok warn=$warn fail=$fail"
if [[ "$fail" -gt 0 ]]; then
  echo "EXT-5 PREFLIGHT: FAIL"
  exit 1
fi
echo "EXT-5 PREFLIGHT: PASS (warn=$warn)"
exit 0
