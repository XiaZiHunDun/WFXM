#!/usr/bin/env bash
# Owner WeChat scenario sim — manifest-driven handler tests (no iLink).
#
# Usage:
#   bash scripts/butler-wechat-owner-sim.sh                    # all tracks (slow)
#   bash scripts/butler-wechat-owner-sim.sh --quick              # core+slash+memory+search
#   bash scripts/butler-wechat-owner-sim.sh --track core,memory
#   bash scripts/butler-wechat-owner-sim.sh --list
#   bash scripts/butler-wechat-owner-sim.sh --strict             # prefer/expect tools 硬断言
#
# Skip (exit 0): BUTLER_WECHAT_OWNER_SIM=0 or no LLM key
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

if [[ "${BUTLER_WECHAT_OWNER_SIM:-1}" == "0" ]]; then
  echo "skip: BUTLER_WECHAT_OWNER_SIM=0"
  exit 0
fi

QUICK=0
STRICT=0
LIST=0
TRACKS=""
JSON_OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick) QUICK=1 ;;
    --strict) STRICT=1 ;;
    --list) LIST=1 ;;
    --track)
      shift
      TRACKS="${1:-}"
      ;;
    --track=*) TRACKS="${1#--track=}" ;;
    --json-out)
      shift
      JSON_OUT="${1:-}"
      ;;
    --json-out=*) JSON_OUT="${1#--json-out=}" ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
  shift
done

exec python3 - "$QUICK" "$STRICT" "$LIST" "$TRACKS" "$JSON_OUT" <<'PY'
import json
import os
import sys

from butler.gateway.wechat_scenario_sim import (
    load_wechat_scenario_manifest,
    list_manifest_tracks,
    run_wechat_scenario_sim,
)

quick = sys.argv[1] == "1"
strict = sys.argv[2] == "1"
list_only = sys.argv[3] == "1"
tracks_arg = sys.argv[4].strip()
json_out = sys.argv[5].strip()

manifest = load_wechat_scenario_manifest()
if manifest is None:
    print("FAIL: .butler/simulation/wechat-owner-scenarios.yaml not found")
    raise SystemExit(1)

if list_only:
    for row in list_manifest_tracks(manifest):
        print(f"  {row['id']:10} quick={row['quick']} mcp={row['requires_mcp']} "
              f"cases={row['cases']}  {row['title']}")
    raise SystemExit(0)

has_llm = any(
    os.getenv(k, "").strip()
    for k in (
        "MINIMAX_API_KEY", "MINIMAX_CN_API_KEY",
        "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    )
)
if not has_llm:
    print("skip: no LLM API key")
    raise SystemExit(0)

track_ids = None
if tracks_arg:
    track_ids = tuple(t.strip() for t in tracks_arg.split(",") if t.strip())

mode = "quick" if quick else "full"
if strict:
    mode += "+strict"
print(f"wechat-owner-sim ({mode}) manifest={manifest.path.name}")

report = run_wechat_scenario_sim(
    manifest,
    track_ids=track_ids,
    strict=strict,
    quick=quick,
)

for cr in report.cases:
    if cr.skipped:
        print(f"  [skip] {cr.track_id}/{cr.name}: {cr.skip_reason}")
        continue
    mark = "ok" if cr.ok else "FAIL"
    tools = cr.tools or []
    print(f"  [{mark}] {cr.track_id}/{cr.name} ({cr.elapsed_seconds:.1f}s) tools={tools}")
    for err in cr.errors:
        print(f"    error: {err}")
    for warn in cr.warnings:
        print(f"    warn: {warn}")
    if cr.reply_preview:
        print(f"    reply: {cr.reply_preview[:160]}…")

for err in report.errors:
    print(f"error: {err}")

summary = {
    "ok": report.ok,
    "tracks_run": report.tracks_run,
    "cases_run": report.cases_run,
    "cases_passed": report.cases_passed,
    "cases_skipped": report.cases_skipped,
    "errors": report.errors,
    "warnings": report.warnings,
}
print(
    f"\nwechat-owner-sim: {'PASS' if report.ok else 'FAIL'} "
    f"({report.cases_passed}/{report.cases_run} passed, "
    f"{report.cases_skipped} skipped)"
)

if json_out:
    payload = {
        **summary,
        "cases": [
            {
                "track_id": c.track_id,
                "name": c.name,
                "ok": c.ok,
                "skipped": c.skipped,
                "tools": c.tools,
                "errors": c.errors,
                "warnings": c.warnings,
                "elapsed_seconds": c.elapsed_seconds,
            }
            for c in report.cases
        ],
    }
    with open(json_out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"json: {json_out}")

raise SystemExit(0 if report.ok else 1)
PY
