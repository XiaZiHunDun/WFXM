#!/usr/bin/env bash
# EXT-3 pilot: convert stack.yaml ingest_pilot_dirs → .butler/ingest/*.md
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."
PROJECT="${1:-${BUTLER_DEFAULT_PROJECT:-灵文1号}}"
shift || true
exec python3 -m butler.main memory ingest --project "$PROJECT" --reindex "$@"
