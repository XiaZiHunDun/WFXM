#!/usr/bin/env bash
# PROD-P4-B WeChat handler sim (/改 usage · /转交CC · DemoPilot 七步).
#
# Usage:
#   bash scripts/butler-owner-ux-p4b-wechat-sim.sh
#   bash scripts/butler-owner-ux-p4b-wechat-sim.sh --verbose
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

from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.wechat_scenario_sim import (
    load_wechat_scenario_manifest,
    run_wechat_scenario_sim,
)

verbose = sys.argv[1] == "1"
owner = (os.getenv("BUTLER_OWNER_WECHAT_ID") or "owner-p4b-sim").strip()

print("=== PROD-P4-B WeChat sim (handler, no iLink) ===")
manifest = load_wechat_scenario_manifest()
if manifest is None:
    print("FAIL: wechat-owner-scenarios.yaml missing")
    raise SystemExit(1)

report = run_wechat_scenario_sim(
    manifest,
    track_ids=("owner-p4b", "demopilot"),
    owner_id=owner,
    quick=True,
    require_llm=False,
)

failures: list[str] = []
for cr in report.cases:
    if cr.skipped:
        print(f"  [skip] {cr.name}: {cr.skip_reason}")
        continue
    mark = "ok" if cr.ok else "FAIL"
    print(f"  [{mark}] {cr.name} ({cr.elapsed_seconds:.2f}s)")
    if verbose and cr.reply_preview:
        print(f"    ↳ {cr.reply_preview[:240]}")
    elif not cr.ok:
        print(f"    reply: {cr.reply_preview[:240]}")
        for err in cr.errors:
            print(f"    error: {err}")
    if not cr.ok:
        failures.append(cr.name)

print(f"\nwechat-owner-p4b-sim: {'ALL PASS' if not failures else failures}")
raise SystemExit(1 if failures else 0)
PY
