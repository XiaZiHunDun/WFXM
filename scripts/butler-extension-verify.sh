#!/usr/bin/env bash
# Extension Verify (L1): manifest secrets + golden MCP calls.
#
# Usage:
#   bash scripts/butler-extension-verify.sh              # all manifests
#   bash scripts/butler-extension-verify.sh github-readonly
#   bash scripts/butler-extension-verify.sh ext-4 --no-golden
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"
butler_source_env "$ROOT/.env" 2>/dev/null || true

EXT_ID=""
NO_GOLDEN=0
for arg in "$@"; do
  case "$arg" in
    --no-golden) NO_GOLDEN=1 ;;
    *)
      if [[ -z "$EXT_ID" ]]; then
        EXT_ID="$arg"
      fi
      ;;
  esac
done

RUN_GOLDEN=1
if [[ "$NO_GOLDEN" -eq 1 ]]; then
  RUN_GOLDEN=0
fi

python3 - "$EXT_ID" "$RUN_GOLDEN" <<'PY'
import sys
from butler.mcp.extension_verify import (
    verify_all_extensions,
    verify_extension,
    write_verify_cache,
)

ext_id = str(sys.argv[1] or "").strip()
run_golden = sys.argv[2] == "1"

if ext_id:
    report = verify_extension(ext_id, run_golden=run_golden)
    write_verify_cache({report.ext_id: report})
    reports = {report.ext_id: report}
else:
    reports = verify_all_extensions(run_golden=run_golden)

fail = 0
for rid, report in sorted(reports.items()):
    mark = "ok" if report.ok else "FAIL"
    print(f"[{mark}] {rid} @ {report.at}")
    for err in report.errors:
        print(f"  error: {err}")
    for warn in report.warnings:
        print(f"  warn: {warn}")
    for case in report.cases:
        cmark = "ok" if case.ok else ("skip" if case.skipped else "fail")
        print(f"  case {case.tool}: {cmark} — {case.detail}")
    if not report.ok:
        fail += 1

if fail:
    sys.exit(1)
PY
