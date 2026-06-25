#!/usr/bin/env bash
# One-shot: legacy .butler/observations.tsv → observations.db
#
# Usage:
#   bash scripts/butler-observation-migrate.sh --workspace /path/to/project
#   bash scripts/butler-observation-migrate.sh --project LingWen1
#   bash scripts/butler-observation-migrate.sh --workspace /path --force
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$ROOT}:$ROOT"

WORKSPACE=""
PROJECT=""
FORCE=0
JSON=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace) WORKSPACE="${2:-}"; shift 2 ;;
    --project) PROJECT="${2:-}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --json) JSON=1; shift ;;
    -h|--help)
      sed -n '1,8p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

ARGS=()
[[ -n "$WORKSPACE" ]] && ARGS+=(--workspace "$WORKSPACE")
[[ -n "$PROJECT" ]] && ARGS+=(--project "$PROJECT")
[[ "$FORCE" -eq 1 ]] && ARGS+=(--force)
[[ "$JSON" -eq 1 ]] && ARGS+=(--json)
ARGS+=(--migrate)

if [[ -z "$WORKSPACE" && -z "$PROJECT" ]]; then
  echo "FAIL: specify --workspace or --project" >&2
  exit 2
fi

python3 -m butler.main memory observations "${ARGS[@]}"
