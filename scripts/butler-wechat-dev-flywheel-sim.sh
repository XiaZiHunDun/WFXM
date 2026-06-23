#!/usr/bin/env bash
# 模拟微信：Lead 收到「role=dev 禁止 content」写 docs 验收戳（handler，不经 iLink）
#
# Usage:
#   bash scripts/butler-wechat-dev-flywheel-sim.sh
#   bash scripts/butler-wechat-dev-flywheel-sim.sh --no-cleanup
#
# Skip (exit 0): BUTLER_WECHAT_DEV_FLYWHEEL_SIM=0 or no LLM key
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_ENABLE_TERMINAL="${BUTLER_ENABLE_TERMINAL:-1}"
export BUTLER_TERMINAL_PROFILE="${BUTLER_TERMINAL_PROFILE:-dev}"
export BUTLER_DEV_ENGINE="${BUTLER_DEV_ENGINE:-1}"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

NO_CLEANUP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cleanup) NO_CLEANUP=1 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ "${BUTLER_WECHAT_DEV_FLYWHEEL_SIM:-1}" == "0" ]]; then
  echo "skip: BUTLER_WECHAT_DEV_FLYWHEEL_SIM=0"
  exit 0
fi

exec python3 - "$NO_CLEANUP" <<'PY'
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

from butler.core.session_epoch import load_epoch_transcript_rows
from butler.gateway.message_handler import ButlerMessageHandler
from butler.runtime.task_store import get_task

no_cleanup = sys.argv[1] == "1"
today = date.today().isoformat()
# 与真机微信话术一致（非 role-sim 专用名）
md_name = f"dev-flywheel-{today}.md"
md_rel = f"docs/{md_name}"
stamp = f"验收戳 {today}"

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

ns = time.time_ns()
owner = (os.getenv("BUTLER_WECHAT_FLYWHEEL_SIM_OWNER") or f"owner-flywheel-{ns}").strip()
session_key = f"wechat:{owner}:flywheel-{ns}"

handler = ButlerMessageHandler(channel="gateway")


def send(text: str) -> str:
    return handler.handle_message(
        text,
        session_key=session_key,
        platform="wechat",
        external_id=owner,
    ) or ""


def canonical_sk() -> str:
    return handler.resolve_session_key(
        platform="wechat",
        external_id=owner,
        session_key=session_key,
    )


def workspace() -> Path:
    from butler.project.manager import ProjectManager

    proj = ProjectManager().get_current(session_key=canonical_sk())
    if proj is None:
        raise RuntimeError("no active project after /切换")
    return Path(proj.workspace)


def delegate_roles_from_transcript() -> list[str]:
    roles: list[str] = []
    sks = [canonical_sk()]
    # Lead 线程与真实 external_id 绑定时，事件落在 canonical 灵文 session
    for sk in sks:
        for row in load_epoch_transcript_rows(sk, max_lines=400):
            if str(row.get("type") or "") == "delegate_started":
                roles.append(str(row.get("role") or "").strip().lower())
                continue
            if str(row.get("type") or "") != "tool_action":
                continue
            if str(row.get("tool") or "") != "delegate_task":
                continue
            preview = str(row.get("args_preview") or "")
            m = re.search(r'"role"\s*:\s*"([^"]+)"', preview)
            if m:
                roles.append(m.group(1).strip().lower())
    return roles


def last_task_id(reply: str = "") -> str:
    tid = ""
    for row in load_epoch_transcript_rows(canonical_sk(), max_lines=400):
        if str(row.get("type") or "") == "delegate_started":
            tid = str(row.get("task_id") or tid)
    if tid:
        return tid
    m = re.search(r"task_[0-9a-f]{12}", reply or "")
    return m.group(0) if m else ""


errors: list[str] = []
ws = workspace()
target = ws / md_rel
if not no_cleanup and target.is_file():
    target.unlink()
    print(f"removed pre-existing {md_rel} for overwrite sim")
elif target.is_file():
    print(f"pre-existing file ({target.stat().st_size} bytes) — 覆写场景（--no-cleanup）")

print("=== Dev flywheel WeChat sim (真机文件名) ===")
print(f"session: {session_key}")
print(f"target:  {md_rel}")

send("/切换 灵文1号")
send("/新对话")

user_msg = (
    f"请 delegate_task，role=dev（禁止用 content）：\n"
    f"在 docs/ 覆写 {md_name}，正文仅一行「验收戳 {today}」；\n"
    f"即使该文件已存在也必须重新 write_file 覆写；\n"
    f"先 read_file 再 write_file，再 read_file 确认；不要改其它文件。"
)
reply = send(user_msg)
print("\n--- Lead 同步回复 ---")
print(reply[:800])

roles = delegate_roles_from_transcript()
task_id = last_task_id(reply)
print(f"\ncanonical session: {canonical_sk()}")
print(f"\ndelegate roles seen: {roles}")
print(f"task_id: {task_id}")

if not roles:
    errors.append("no delegate_task / delegate_started in transcript")
elif roles[-1] != "dev":
    errors.append(f"expected final delegate role=dev, got {roles[-1]!r}")

if "审核代理" in reply and "开发" not in reply:
    errors.append("Lead reply shows review agent, expected dev")

if "content" in reply.lower() and "开发" not in reply and "dev" not in reply.lower():
    if "已派 content" in reply or "内容代理" in reply:
        errors.append(f"Lead reply routed to content: {reply[:200]!r}")

if task_id:
    deadline = time.time() + 360
    rec = None
    while time.time() < deadline:
        rec = get_task(task_id)
        if rec and str(rec.get("status") or "") in ("completed", "failed"):
            break
        time.sleep(2)
    if rec is None:
        errors.append(f"task record missing: {task_id}")
    else:
        print(f"\ntask status: {rec.get('status')} role={rec.get('role')} success={rec.get('success')}")
        if str(rec.get("role") or "").lower() != "dev":
            errors.append(f"task store role={rec.get('role')!r}, expected dev")
        if not rec.get("success"):
            summary = (rec.get("summary") or "")[:300]
            if "DEV_VERIFY" in summary or "验证" in (rec.get("report_headline") or ""):
                errors.append(f"dev verify gate failed: {summary[:120]}")
            else:
                errors.append(f"delegate failed: {summary}")
else:
    errors.append("no task_id from delegate_started")

if not target.is_file():
    errors.append(f"file missing: {md_rel}")
else:
    body = target.read_text(encoding="utf-8").strip()
    print(f"\nfile ({len(body)} chars):\n{body[:200]}")
    if f"验收戳 {today}" not in body and stamp not in body:
        errors.append(f"file missing one-line stamp {stamp}")
    if body.count("\n") > 2:
        errors.append("file should be one line (at most 2 newlines)")

if errors:
    print("\nFAIL:")
    for e in errors:
        print(f"  - {e}")
    raise SystemExit(1)

print("\nOK: dev flywheel role=dev sim passed")
if no_cleanup:
    print(f"artifact kept: {target}")
PY
