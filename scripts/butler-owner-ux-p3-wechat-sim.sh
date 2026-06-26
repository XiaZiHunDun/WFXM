#!/usr/bin/env bash
# PROD-P3 WeChat handler sim (no iLink) — switch slug, gate copy, optional NL CC hint.
#
# Usage:
#   bash scripts/butler-owner-ux-p3-wechat-sim.sh           # slash cases only
#   bash scripts/butler-owner-ux-p3-wechat-sim.sh --nl      # + one NL CC-route turn (needs LLM key)
#   bash scripts/butler-owner-ux-p3-wechat-sim.sh --verbose
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

VERBOSE=0
RUN_NL=0
for arg in "$@"; do
  case "$arg" in
    --verbose|-v) VERBOSE=1 ;;
    --nl) RUN_NL=1 ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

export BUTLER_MCP_MAX_SERVERS="${BUTLER_MCP_MAX_SERVERS:-4}"

exec python3 - "$VERBOSE" "$RUN_NL" <<'PY'
import os
import sys
import time

from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.outbound_files import expand_reply_with_wechat_attachments
from butler.gateway.wechat_scenario_sim import (
    load_wechat_scenario_manifest,
    run_wechat_scenario_sim,
)

verbose = sys.argv[1] == "1"
run_nl = sys.argv[2] == "1"
owner = (os.getenv("BUTLER_OWNER_WECHAT_ID") or "owner-wechat-p3-sim").strip()

print("=== PROD-P3 WeChat sim (handler, no iLink) ===")
print(f"WORKFLOW_AUTO_RESUME={os.getenv('BUTLER_WORKFLOW_AUTO_RESUME', '')!r}")
print(f"DELEGATE_PROGRESS={os.getenv('BUTLER_GATEWAY_DELEGATE_PROGRESS_NOTIFY', '')!r}")

manifest = load_wechat_scenario_manifest()
if manifest is None:
    print("FAIL: wechat-owner-scenarios.yaml missing")
    raise SystemExit(1)

report = run_wechat_scenario_sim(
    manifest,
    track_ids=("owner-p3",),
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
        print(f"    ↳ {cr.reply_preview}")
    elif not cr.ok:
        print(f"    reply: {cr.reply_preview[:240]}")
        for err in cr.errors:
            print(f"    error: {err}")
    if not cr.ok:
        failures.append(cr.name)

# Gate template smoke (no pending gate file needed)
from butler.gateway.gate_reply_templates import workflow_gate_pending_hint

hint = workflow_gate_pending_hint(workflow="novel-factory", step_id="draft")
if "下一步" not in hint:
    failures.append("gate_template")
    print("  [FAIL] gate template missing 下一步")
else:
    print("  [ok] gate template workflow pending")

if run_nl:
    has_key = any(os.getenv(k, "").strip() for k in (
        "MINIMAX_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    ))
    if not has_key:
        print("  [skip] NL CC-route: no LLM key")
    else:
        handler = ButlerMessageHandler(channel="gateway")
        sk = f"wechat:{owner}:p3-nl-{time.time_ns()}"
        msg = "请把整个 WFXM 代码库大规模重构一遍，全部模块迁移"
        print(f"\n== NL CC-route hint ==\nIN:  {msg}")
        t0 = time.time()
        raw = handler.handle_message(msg, session_key=sk, platform="wechat", external_id=owner) or ""
        out = expand_reply_with_wechat_attachments(raw)
        elapsed = time.time() - t0
        preview = raw.replace("\n", " ")[:320]
        print(f"OUT ({elapsed:.1f}s): {preview}{'…' if len(raw) > 320 else ''}")
        cc_markers = ("CC", "本机", "重构", "/cc-bridge", "/分工", "验收")
        if any(m in out for m in cc_markers):
            print("  [ok] NL CC-route (reply mentions CC/分工/验收)")
        else:
            health = handler.get_session_health(sk) or {}
            if health.get("cc_route_banner"):
                print("  [ok] NL CC-route (cc_route_banner in health)")
            else:
                failures.append("NL CC-route")
                print("  [FAIL] NL CC-route: no CC/分工 hint in reply or health")

print(f"\nwechat-owner-p3-sim: {'ALL PASS' if not failures else failures}")
raise SystemExit(1 if failures else 0)
PY
