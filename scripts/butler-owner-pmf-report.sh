#!/usr/bin/env bash
# Owner PMF weekly report (PROD-P4-08). Requires BUTLER_OWNER_PMF_METRICS=1.
#
# Usage:
#   bash scripts/butler-owner-pmf-report.sh
#   bash scripts/butler-owner-pmf-report.sh --days 14
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

DAYS=7
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days)
      DAYS="${2:-7}"
      shift 2
      ;;
    --days=*)
      DAYS="${1#--days=}"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

python3 - "$DAYS" <<'PY'
import sys

from butler.ops.owner_pmf_metrics import format_owner_pmf_report

print(format_owner_pmf_report(days=int(sys.argv[1])))
PY
