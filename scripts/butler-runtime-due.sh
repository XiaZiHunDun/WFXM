#!/usr/bin/env bash
# Run all due runtime jobs (readonly execute; mutating notify for approval).
# Usage: butler-runtime-due.sh [项目名]
#   无参数: --all-projects（所有含 runtime/jobs.yaml 的项目）
#   有参数: 仅指定项目
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PROJECT="${1:-}"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
if [[ -z "$PROJECT" ]]; then
  exec butler runtime due --all-projects
fi
exec butler runtime due --project "$PROJECT"
