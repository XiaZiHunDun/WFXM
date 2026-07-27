#!/usr/bin/env bash
# P0: purge MB5 benchmark filler + seed owner experience pointers (skill:/tool:).
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
TENANT="${BUTLER_TENANT:-default}"
exec python3 -m butler.memory.owner_experience_seed --tenant "${TENANT}" "$@"
