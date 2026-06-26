#!/usr/bin/env bash
# Owner 首周运营节奏 — handler 模拟（不经 iLink）+ G1-04 /反馈 烟测。
#
# 覆盖 playbook：/简报 · /帮助 · /切换 · /反馈(OT2) · P3 切换纠错
#
# Usage:
#   bash scripts/butler-owner-week1-ops-sim.sh
#   bash scripts/butler-owner-week1-ops-sim.sh --log-g1   # 周打卡写 pilot-log
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

LOG_G1=0
for arg in "$@"; do
  case "$arg" in
    --log-g1) LOG_G1=1 ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

export BUTLER_MCP_MAX_SERVERS="${BUTLER_MCP_MAX_SERVERS:-4}"

echo "=== Owner 首周 ops sim (handler, no iLink) ==="
echo ""

echo "--- 1/4 owner-ux track ---"
bash "$ROOT/scripts/butler-wechat-owner-ux-sim.sh"

echo ""
echo "--- 2/4 PROD-P3 track ---"
bash "$ROOT/scripts/butler-owner-ux-p3-wechat-sim.sh"

echo ""
echo "--- 3/4 G1-04 /反馈 handler 烟测 ---"
python3 - <<'PY'
import os
import time

from butler.gateway.message_handler import ButlerMessageHandler
from butler.ops.boundary_observability import g1_04_observation_window_status
from butler.ops.owner_feedback import is_owner_explicit_trigger

owner = (os.getenv("BUTLER_OWNER_WECHAT_ID") or "owner-week1-sim").strip()
handler = ButlerMessageHandler(channel="gateway")
sk = f"wechat:{owner}:week1-feedback-{time.time_ns()}"

before = g1_04_observation_window_status()
owner_explicit_before = int(before.get("feedback_owner_explicit") or 0)

msg = "/反馈 周运营模拟：委派结果应只读检查，勿改生产配置"
reply = handler.handle_message(msg, session_key=sk, platform="wechat", external_id=owner) or ""
if "OT2" not in reply and "已记录" not in reply:
    print(f"FAIL: unexpected /反馈 reply: {reply[:200]}")
    raise SystemExit(1)
print(f"  [ok] /反馈 ack: {reply.splitlines()[0]}")

after = g1_04_observation_window_status()
owner_explicit_after = int(after.get("feedback_owner_explicit") or 0)
if owner_explicit_after <= owner_explicit_before:
    print(
        f"WARN: feedback_owner_explicit {owner_explicit_before} -> {owner_explicit_after} "
        "(audit 可能未即时刷新；见 eval_feedback)"
    )
else:
    print(f"  [ok] feedback_owner_explicit {owner_explicit_before} -> {owner_explicit_after}")

# Spot-check last audit row trigger
from butler.config import get_butler_home

fb_path = get_butler_home() / "audit" / "eval_feedback.jsonl"
found = False
if fb_path.is_file():
    tail = fb_path.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]
    for line in tail:
        if "周运营模拟" in line and "owner_hard_feedback" in line:
            found = True
            break
if found:
    print("  [ok] eval_feedback row with owner_hard_feedback")
else:
    print("  [warn] recent eval_feedback 未命中本 sim 行（非致命）")
PY

echo ""
echo "--- 4/4 G1-04 weekly check-in ---"
G1_ARGS=()
[[ "$LOG_G1" -eq 1 ]] && G1_ARGS+=(--log)
bash "$ROOT/scripts/butler-g1-04-weekly-checkin.sh" "${G1_ARGS[@]}"

echo ""
echo "OWNER-WEEK1-OPS-SIM: PASS"
echo "真机补充：微信按 docs/guides/owner-first-week-2026-06.md 走一遍；EXT-5 见 ext5-wechat-verify-2026-06.md"
