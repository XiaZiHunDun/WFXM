#!/usr/bin/env bash
# DemoPilot（普通试点项目）端到端冒烟：preflight + runtime jobs
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROJECT="普通试点项目"

if [[ -f .env ]]; then
  set -a
  set +u
  # shellcheck disable=SC1091
  source .env
  set -u
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "== 1/3 project preflight =="
butler project preflight --project "$PROJECT"

echo ""
echo "== 2/3 runtime pilot-heartbeat =="
butler runtime run pilot-heartbeat --project "$PROJECT" --no-notify

echo ""
echo "== 3/3 runtime test-unit-smoke (force, enabled=false by default) =="
butler runtime run test-unit-smoke --project "$PROJECT" --no-notify --force

echo ""
echo "DemoPilot smoke: ALL PASSED"
