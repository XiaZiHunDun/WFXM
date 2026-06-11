#!/usr/bin/env bash
# Phase 4: Cross-dimension assistant health (memory vs dev vs wechat vs routing).
#
# Usage:
#   bash scripts/butler-eval-assistant-health.sh
#   bash scripts/butler-eval-assistant-health.sh --push
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

PUSH=0
LOOKBACK=168

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH=1 ;;
    --lookback=*) LOOKBACK="${1#--lookback=}" ;;
    -h|--help)
      echo "Usage: $0 [--push] [--lookback=HOURS]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<PY
import json
from butler.ops.assistant_health import (
    collect_assistant_health,
    format_assistant_health_lines,
    push_assistant_health_scores,
)

report = collect_assistant_health(lookback_hours=float("$LOOKBACK"))
print(json.dumps(report.summary(), ensure_ascii=False, indent=2))
print()
for line in format_assistant_health_lines(report):
    print(line)
if $PUSH:
    push = push_assistant_health_scores(report)
    print()
    print(f"LangFuse: pushed {push.get('scores_pushed', 0)} assistant_health scores")
PY
