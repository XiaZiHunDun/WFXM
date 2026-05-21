#!/usr/bin/env bash
# Rebuild ~/.butler/.../memory_vectors.db from experience + project MEMORY (local, no cloud).
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
exec python3 -m butler.main memory-reindex "$@"
