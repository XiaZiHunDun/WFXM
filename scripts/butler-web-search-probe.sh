#!/usr/bin/env bash
# Probe web_search from gateway-equivalent env (same .env + PYTHONPATH as systemd unit).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"
butler_source_env "$ROOT/.env" 2>/dev/null || true
export PYTHONPATH="$ROOT"
PYTHON="$(command -v python3)"
exec "$PYTHON" -m butler.tools.web_search_probe "$@"
