#!/usr/bin/env bash
# G1-12 / G1-12b: network search routing policy + optional handler sim + probe.
#
# Usage:
#   bash scripts/butler-web-search-route-sim.sh                      # policy only (~2s)
#   bash scripts/butler-web-search-route-sim.sh --handler            # + LLM handler (~60s, soft)
#   bash scripts/butler-web-search-route-sim.sh --handler --strict-handler  # 发版前：prefer 工具硬断言
#   bash scripts/butler-web-search-route-sim.sh --with-probe         # + web_search live probe
#
# Skip (exit 0): BUTLER_WEB_SEARCH_ROUTE_SIM=0
# Handler skip: BUTLER_WEB_SEARCH_ROUTE_HANDLER=0
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

if [[ "${BUTLER_WEB_SEARCH_ROUTE_SIM:-1}" == "0" ]]; then
  echo "skip: BUTLER_WEB_SEARCH_ROUTE_SIM=0"
  exit 0
fi

WITH_PROBE=0
WITH_HANDLER=0
STRICT_HANDLER=0
for arg in "$@"; do
  case "$arg" in
    --with-probe) WITH_PROBE=1 ;;
    --handler) WITH_HANDLER=1 ;;
    --strict-handler) STRICT_HANDLER=1; WITH_HANDLER=1 ;;
  esac
done

exec python3 - "$WITH_PROBE" "$WITH_HANDLER" "$STRICT_HANDLER" <<'PY'
import json
import os
import sys

from butler.tools.network_route_verify import (
    load_network_route_manifest,
    run_handler_route_cases,
    run_policy_golden_cases,
    run_web_search_probe,
)

with_probe = sys.argv[1] == "1"
with_handler = sys.argv[2] == "1"
strict_handler = sys.argv[3] == "1"
manifest = load_network_route_manifest()
if manifest is None:
    print("FAIL: network-search-routes.yaml not found")
    raise SystemExit(1)

print(f"network-route policy verify ({len(manifest.golden_cases)} cases)")
report = run_policy_golden_cases(manifest)
for case in report.cases:
    mark = "ok" if case.get("ok") else "FAIL"
    code = case.get("code")
    print(f"  [{mark}] {case['name']} tool={case['tool']} code={code!r}")
for err in report.errors:
    print(f"  error: {err}")

if not report.ok:
    print("policy verify: FAIL")
    raise SystemExit(1)
print("policy verify: ok")

handler_fail = 0
if with_handler:
    if os.getenv("BUTLER_WEB_SEARCH_ROUTE_HANDLER", "1").strip() == "0":
        print("\nhandler sim: skip (BUTLER_WEB_SEARCH_ROUTE_HANDLER=0)")
    else:
        has_llm = any(
            os.getenv(k, "").strip()
            for k in (
                "MINIMAX_API_KEY",
                "MINIMAX_CN_API_KEY",
                "DEEPSEEK_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
            )
        )
        if not has_llm:
            print("\nhandler sim: skip (no LLM API key)")
        else:
            mode = "strict" if strict_handler else "soft"
            print(f"\nhandler route sim ({len(manifest.handler_cases)} cases, {mode})")
            owner = os.getenv("BUTLER_OWNER_WECHAT_ID", "owner-route-handler-sim")
            project = os.getenv("BUTLER_WEB_SEARCH_ROUTE_PROJECT", "")
            hreport = run_handler_route_cases(
                manifest,
                owner_id=owner,
                project_name=project,
                strict=strict_handler,
            )
            for case in hreport.cases:
                mark = "ok" if case.get("ok") else "FAIL"
                tools = case.get("tools") or []
                print(f"  [{mark}] {case['name']} tools={tools}")
                for warn in case.get("warnings") or []:
                    print(f"    warn: {warn}")
            for err in hreport.errors:
                print(f"  error: {err}")
            for warn in hreport.warnings:
                print(f"  warn: {warn}")
            if hreport.ok:
                print(f"handler verify: ok ({mode})")
            else:
                print(f"handler verify: FAIL ({mode})")
                handler_fail = 1

if with_probe:
    print("")
    print(f"web_search probe: {manifest.probe_query!r}")
    probe_ok, payload = run_web_search_probe(manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not probe_ok:
        print("probe: FAIL (network/proxy — non-fatal if policy ok)")
        raise SystemExit(2 if not handler_fail else 3)

if handler_fail:
    raise SystemExit(1)
PY
