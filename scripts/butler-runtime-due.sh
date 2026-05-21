#!/usr/bin/env bash
# Run all due runtime jobs for a project (readonly execute; mutating notify for approval).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PROJECT="${1:-灵文1号}"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
exec butler runtime due --project "$PROJECT"
