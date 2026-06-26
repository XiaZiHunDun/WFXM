#!/usr/bin/env bash
# EXT-5 Verify: preflight + extension cache + MCP connect + handler sim (no iLink).
#
# Usage:
#   bash scripts/butler-extension-ext5-verify.sh           # full
#   bash scripts/butler-extension-ext5-verify.sh --quick   # skip slow conversion sim
#
# After this passes, complete 真机 phrases in docs/guides/ext5-wechat-verify-2026-06.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"
butler_source_env "$ROOT/.env" 2>/dev/null || true

export BUTLER_MCP_MAX_SERVERS="${BUTLER_MCP_MAX_SERVERS:-4}"

QUICK=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
  esac
done

echo "=== EXT-5 Verify (automated) ==="
echo "BUTLER_MCP_MAX_SERVERS=${BUTLER_MCP_MAX_SERVERS}"

bash "$ROOT/scripts/butler-extension-ext5-preflight.sh"
bash "$ROOT/scripts/butler-extension-verify.sh" markitdown-ingest
bash "$ROOT/scripts/butler-extension-ext5-gate.sh"

echo ""
echo "=== MCP status (markitdown must be [ok]) ==="
python3 - <<'PY'
import sys
from butler.mcp.registry_hook import mcp_status_lines

lines = mcp_status_lines("ext5-verify")
for line in lines:
    print(line)
md = [l for l in lines if "markitdown" in l.lower()]
if not any("[ok]" in l for l in md):
    print("FAIL: markitdown MCP not connected", file=sys.stderr)
    raise SystemExit(1)
print("markitdown MCP: ok")
PY

if [[ "$QUICK" -eq 1 ]]; then
  bash "$ROOT/scripts/butler-extension-ext5-wechat-sim.sh" --quick
else
  bash "$ROOT/scripts/butler-extension-ext5-wechat-sim.sh"
fi

echo ""
echo "EXT-5 VERIFY (automated): PASS"
echo "真机：微信发 manifest verify_phrases — 见 docs/guides/ext5-wechat-verify-2026-06.md"
