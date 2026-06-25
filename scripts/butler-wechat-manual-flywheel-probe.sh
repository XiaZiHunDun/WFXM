#!/usr/bin/env bash
# 月度 Dev 飞轮 · 真机话术等价探针（handler + Owner session，不经用户手打微信）
#
# 与 docs/guides/dev-flywheel-monthly.md §2A 话术一致；出站可选推微信摘要。
#
# Usage:
#   bash scripts/butler-wechat-manual-flywheel-probe.sh
#   bash scripts/butler-wechat-manual-flywheel-probe.sh --push   # 结果推送到 Owner 微信
#   bash scripts/butler-wechat-manual-flywheel-probe.sh --log
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

PUSH=0
LOG=0
for arg in "$@"; do
  case "$arg" in
    --push) PUSH=1 ;;
    --log) LOG=1 ;;
    -h|--help)
      sed -n '1,10p' "$0"
      exit 0
      ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

exec python3 - "$PUSH" "$LOG" <<'PY'
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

from butler.core.session_epoch import load_epoch_transcript_rows
from butler.gateway.message_handler import ButlerMessageHandler
from butler.runtime.task_store import get_task

push = sys.argv[1] == "1"
do_log = sys.argv[2] == "1"
today = date.today().isoformat()
md_name = f"dev-flywheel-manual-{today}.md"
md_rel = f"docs/{md_name}"
stamp = f"月度验收 {today}"

owner = (os.getenv("BUTLER_OWNER_WECHAT_ID") or "").strip()
if not owner:
    print("FAIL: BUTLER_OWNER_WECHAT_ID unset")
    raise SystemExit(1)

has_llm = any(
    os.getenv(k, "").strip()
    for k in (
        "MINIMAX_API_KEY", "MINIMAX_CN_API_KEY",
        "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    )
)
if not has_llm:
    print("FAIL: no LLM API key")
    raise SystemExit(1)

ns = time.time_ns()
session_key = f"wechat:{owner}:manual-flywheel-{ns}"
handler = ButlerMessageHandler(channel="gateway")
errors: list[str] = []


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
        raise RuntimeError("no active project")
    return Path(proj.workspace)


def last_task_id(reply: str = "") -> str:
    tid = ""
    for row in load_epoch_transcript_rows(canonical_sk(), max_lines=400):
        if str(row.get("type") or "") == "delegate_started":
            tid = str(row.get("task_id") or tid)
    if tid:
        return tid
    m = re.search(r"task_[0-9a-f]{12}", reply or "")
    return m.group(0) if m else ""


print("=== Manual flywheel probe (§2A 灵文1号) ===")
print(f"owner: {owner[:12]}…")
print(f"target: {md_rel}")

ws = workspace()
target = ws / md_rel
if target.is_file():
    target.unlink()
    print(f"removed pre-existing {md_rel}")

send("/切换 灵文1号")
send("/新对话")

user_msg = (
    f"请 delegate_task，role=dev（禁止 content）：\n"
    f"在 docs/ 写 {md_name}，正文仅一行「{stamp}」；\n"
    f"先 read_file 确认不存在再 write_file，写后再 read_file 确认；不要改其它文件。"
)
reply = send(user_msg)
print("\n--- Lead reply (trunc) ---")
print(reply[:600])

task_id = last_task_id(reply)
if not task_id:
    errors.append("no task_id from delegate")
elif "开发" not in reply and "委派" not in reply and "task_" not in reply:
    errors.append(f"reply missing delegate cues: {reply[:120]!r}")

if task_id:
    deadline = time.time() + 420
    rec = None
    while time.time() < deadline:
        rec = get_task(task_id)
        if rec and str(rec.get("status") or "") in ("completed", "failed"):
            break
        time.sleep(2)
    if rec is None:
        errors.append(f"task missing: {task_id}")
    else:
        print(f"\ntask: {task_id} status={rec.get('status')} role={rec.get('role')} success={rec.get('success')}")
        if str(rec.get("role") or "").lower() != "dev":
            errors.append(f"task role={rec.get('role')!r}")
        if not rec.get("success"):
            errors.append(f"delegate failed: {(rec.get('summary') or '')[:200]}")

if not target.is_file():
    errors.append(f"file missing: {md_rel}")
else:
    body = target.read_text(encoding="utf-8").strip()
    print(f"\nfile:\n{body}")
    if stamp not in body:
        errors.append(f"missing stamp {stamp!r}")

detail = send("/详细")
print("\n--- /详细 (trunc) ---")
print(detail[:400])
if task_id and task_id not in detail and md_name not in detail:
    if "无" in detail and "委派" in detail:
        errors.append("/详细 missing task evidence")

diag = send("/诊断")
print("\n--- /诊断 (trunc) ---")
print(diag[:300])
if "僵死" in diag or "stuck" in diag.lower():
    errors.append("/诊断 reports stuck delegate")

if re.search(r"(?<!/projects/)LingWen1/docs", reply) or (
    "File not found" in reply and "LingWen1/" in reply
):
    errors.append("path error LingWen1/docs relative prefix in Lead reply")

if errors:
    print("\nFAIL:")
    for e in errors:
        print(f"  - {e}")
    result = "FAIL"
    exit_code = 1
else:
    print("\nOK: manual flywheel probe passed")
    result = f"PASS task={task_id} file={md_rel}"
    exit_code = 0

if push:
    try:
        from butler.runtime.notify import push_runtime_message, resolve_owner_wechat_chat_id

        cid = resolve_owner_wechat_chat_id()
        if cid and os.getenv("WECHAT_TOKEN", "").strip():
            body = (
                f"月度 Dev 飞轮真机话术探针 {result}\n"
                f"项目：灵文1号\n"
                f"文件：{md_rel}\n"
                f"任务：{task_id or 'n/a'}\n"
                f"（handler+Owner 会话等价验收，非手打微信）"
            )
            ok = push_runtime_message("[Butler] 月度飞轮探针", body[:900])
            print(f"\nWeChat push: {'ok' if ok else 'failed'}")
        else:
            print("\nWeChat push: skipped (no token/chat_id)")
    except Exception as exc:
        print(f"\nWeChat push error: {exc}")

if do_log and exit_code == 0:
    log_path = Path("projects/LingWen1/docs/pilot-log.md")
    row = f"| {today} | **月度飞轮真机话术探针** | handler+Owner {result} |"
    if log_path.is_file() and row not in log_path.read_text(encoding="utf-8"):
        text = log_path.read_text(encoding="utf-8")
        text = text.replace(
            "|------|------|------|\n",
            f"|------|------|------|\n{row}\n",
            1,
        )
        log_path.write_text(text, encoding="utf-8")
        print(f"Appended pilot-log: {log_path}")

raise SystemExit(exit_code)
PY
