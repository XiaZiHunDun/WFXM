#!/usr/bin/env bash
# Run one Butler runtime job (phase 3a). Used by cron/systemd or manual ops.
# Usage: bash scripts/butler-runtime-run.sh <job_id> [project_name]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PROJECT="${2:-灵文1号}"
JOB_ID="${1:?job id required}"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
exec butler runtime run "$JOB_ID" --project "$PROJECT"
