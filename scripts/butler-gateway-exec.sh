#!/bin/bash
# Gateway ExecStart wrapper: safe PATH before .env (nvm + /usr/bin) for MCP npx/uvx.
set -euo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lib/butler-systemd-install.sh
source "$ROOT/scripts/lib/butler-systemd-install.sh"
# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"

export PYTHONPATH="$ROOT"
butler_source_env "$ROOT/.env" 2>/dev/null || true

PYTHON="$(butler_resolve_python3)"
exec "$PYTHON" -m butler.main gateway "$@"
