#!/usr/bin/env bash
# Owner UX slash-command sim — handler only, no LLM / iLink.
#
# Simulates WeChat messages for P0–P2 Owner surfaces:
#   /帮助 /高级 /今日 /简报 /分工 /诊断 /项目概况 /切换
#
# Usage:
#   bash scripts/butler-wechat-owner-ux-sim.sh
#   bash scripts/butler-wechat-owner-ux-sim.sh --verbose
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
if manifest is None:
    print("FAIL: wechat-owner-scenarios.yaml not found")
    raise SystemExit(1)

owner = (os.getenv("BUTLER_OWNER_WECHAT_ID") or "owner-wechat-ux-sim").strip()
print(f"wechat-owner-ux-sim (handler, no LLM) owner={owner[:20]}…")

report = run_wechat_scenario_sim(
    manifest,
    track_ids=("owner-ux",),
    owner_id=owner,
    quick=True,
    require_llm=False,
)

for cr in report.cases:
    if cr.skipped:
        print(f"  [skip] {cr.track_id}/{cr.name}: {cr.skip_reason}")
        continue
    mark = "ok" if cr.ok else "FAIL"
    print(f"  [{mark}] {cr.name} ({cr.elapsed_seconds:.2f}s)")
    if verbose and cr.reply_preview:
        print(f"    ↳ {cr.reply_preview}")
    elif not cr.ok and cr.reply_preview:
        print(f"    reply: {cr.reply_preview[:200]}")
    for err in cr.errors:
        print(f"    error: {err}")

print(
    f"\nwechat-owner-ux-sim: {'PASS' if report.ok else 'FAIL'} "
    f"({report.cases_passed}/{report.cases_run} passed)"
)
raise SystemExit(0 if report.ok else 1)
PY
