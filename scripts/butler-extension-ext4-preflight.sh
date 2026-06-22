#!/usr/bin/env bash
# EXT-4 preflight: GitHub OpenAPI MCP (path A) readiness.
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

echo "EXT-4 GitHub OpenAPI MCP preflight"

if command -v node >/dev/null 2>&1; then
  node_ver="$(node --version 2>/dev/null | sed 's/^v//' || echo '0')"
  node_major="${node_ver%%.*}"
  if [[ "${node_major:-0}" -ge 18 ]]; then
    _pass "node: $(command -v node) (v${node_ver})"
  else
    _warn "node v${node_ver} < 18"
  fi
else
  _fail "node not in PATH"
fi

if command -v npx >/dev/null 2>&1; then
  _pass "npx: $(command -v npx)"
else
  _fail "npx not in PATH"
fi

if PYTHONPATH="$ROOT" python3 -c "import mcp" 2>/dev/null; then
  _pass "python mcp SDK installed"
else
  _fail "pip install butler-system[mcp]"
fi

if [[ "${BUTLER_MCP_ENABLED:-0}" == "1" ]]; then
  _pass "BUTLER_MCP_ENABLED=1"
else
  _warn "BUTLER_MCP_ENABLED not 1"
fi

case "${BUTLER_MCP_STDIO_ALLOW_COMMANDS:-python,python3,uvx}" in
  *npx*) _pass "BUTLER_MCP_STDIO_ALLOW_COMMANDS includes npx" ;;
  *) _warn "BUTLER_MCP_STDIO_ALLOW_COMMANDS lacks npx" ;;
esac

repo_spec="$ROOT/.butler/openapi/github-readonly.yml"
pin_spec="$HOME/.butler/openapi/github-readonly.yml"
if [[ -f "$pin_spec" ]]; then
  _pass "pinned OpenAPI spec: $pin_spec"
elif [[ -f "$repo_spec" ]]; then
  _warn "spec not pinned — run: bash scripts/butler-github-openapi-spec-install.sh"
else
  _fail "missing repo spec at $repo_spec"
fi

token="${GITHUB_TOKEN:-${GITHUB_PERSONAL_ACCESS_TOKEN:-}}"
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
for key in ("GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"):
    val = str(data.get(key) or "").strip()
    if val:
        print(val)
        break
PY
)"
fi
if [[ -n "$token" ]]; then
  _pass "GITHUB_TOKEN set (len=${#token})"
elif [[ -n "$secrets_token" ]]; then
  if [[ "${BUTLER_MCP_ENABLED:-0}" == "1" ]]; then
    _fail "GITHUB_TOKEN in secrets.yaml but not process env — run: bash scripts/butler-github-token-sync.sh"
  else
    _warn "GITHUB_TOKEN only in secrets.yaml — sync before MCP live calls"
  fi
else
  if [[ "${BUTLER_MCP_ENABLED:-0}" == "1" ]]; then
    _fail "GITHUB_TOKEN unset — add to ~/.butler/secrets.yaml then bash scripts/butler-github-token-sync.sh"
  else
    _warn "GITHUB_TOKEN unset — add to ~/.butler/secrets.yaml or .env before live calls"
  fi
fi

found_github=0
for cfg in "$HOME/.butler/mcp.yaml" "$ROOT/.butler/mcp.yaml"; do
  if [[ -f "$cfg" ]] && grep -qE '^[[:space:]]*github:' "$cfg" 2>/dev/null; then
    _pass "github block in $cfg"
    found_github=1
    break
  fi
done
if [[ "$found_github" -eq 0 ]]; then
  _warn "no github server in mcp.yaml — run: bash scripts/butler-extension-ext4-integrate.sh"
fi

echo ""
echo "summary: ok=$ok warn=$warn fail=$fail"
if [[ "$fail" -gt 0 ]]; then
  echo "See docs/plans/active/extension-candidates/ext-4-second-openapi-2026-06.md"
  exit 1
fi
exit 0
