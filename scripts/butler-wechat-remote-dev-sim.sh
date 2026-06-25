#!/usr/bin/env bash
# Remote-dev handler sim — /沙箱 /cc-bridge /分工 (no iLink, no LLM).
#
# Usage:
#   bash scripts/butler-wechat-remote-dev-sim.sh
#   bash scripts/butler-wechat-remote-dev-sim.sh --verbose
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

VERBOSE=0
for arg in "$@"; do
  case "$arg" in
    --verbose|-v) VERBOSE=1 ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

exec python3 - "$VERBOSE" <<'PY'
import os
import sys

from butler.gateway.wechat_scenario_sim import (
    load_wechat_scenario_manifest,
    run_wechat_scenario_sim,
)

verbose = sys.argv[1] == "1"
manifest = load_wechat_scenario_manifest()
owner = (os.getenv("BUTLER_OWNER_WECHAT_ID") or "owner-wechat-sim").strip()
print(f"wechat-remote-dev-sim owner={owner[:20]}… profile={os.getenv('BUTLER_ENV_PROFILE', '?')}")

report = run_wechat_scenario_sim(
    manifest,
    track_ids=("remote-dev",),
    owner_id=owner,
    quick=True,
    require_llm=False,
)

for cr in report.cases:
    if cr.skipped:
        print(f"  [skip] {cr.name}: {cr.skip_reason}")
        continue
    mark = "ok" if cr.ok else "FAIL"
    print(f"  [{mark}] {cr.name} ({cr.elapsed_seconds:.2f}s)")
    if verbose and cr.reply_preview:
        print(f"    ↳ {cr.reply_preview[:400]}")
    elif not cr.ok and cr.reply_preview:
        print(f"    reply: {cr.reply_preview[:200]}")
    for err in cr.errors:
        print(f"    error: {err}")

print(
    f"\nwechat-remote-dev-sim: {'PASS' if report.ok else 'FAIL'} "
    f"({report.cases_passed}/{report.cases_run} passed)"
)
raise SystemExit(0 if report.ok else 1)
PY
