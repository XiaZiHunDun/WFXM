"""Gateway message handler helper functions.

Extracted from message_handler.py. Contains text normalization,
command classification, project overview building, and session
management utilities.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from butler.core.agent_loop import AgentLoop

logger = logging.getLogger(__name__)

def _normalize_switch_request(text: str) -> str | None:
    """Map「切换到 <项目>」to ``/切换 <项目>`` (WeChat natural phrasing)."""
    stripped = (text or "").strip().rstrip("。.!！?？")
    _switch_prefixes = ("切换到", "切换至", "切换去", "切换回")
    if stripped.startswith("切换") and not any(
        stripped.startswith(p) for p in _switch_prefixes
    ):
        name = stripped[len("切换") :].strip().rstrip("。.!！?？")
        if name and not name.startswith("/"):
            return f"/切换 {name}"
    for prefix in (
        "切换到",
        "切换至",
        "切换去",
        "切换回",
        "现在切到",
        "现在切回",
        "切到",
        "切回",
        "把项目切回去",
        "把项目切回",
    ):
        if stripped.startswith(prefix):
            name = stripped[len(prefix) :].strip().rstrip("。.!！?？")
            if name:
                return f"/切换 {name}"
    if stripped.startswith("切回去"):
        name = stripped[len("切回去") :].strip().rstrip("。.!！?？")
        if name:
            return f"/切换 {name}"
    return None


def _normalize_status_request(text: str) -> str | None:
    """Map project-status questions to ``/状态``."""
    stripped = (text or "").strip().rstrip("？?").strip()
    purpose_hints = (
        "做什么",
        "干什么",
        "用途",
        "目的",
        "介绍",
        "是干嘛",
        "干啥",
        "干什么用",
        "用来做什么",
        "用来干什么",
    )
    if any(hint in stripped for hint in purpose_hints):
        return None
    if stripped in (
        "当前在哪个项目",
        "当前是什么项目",
        "当前什么项目",
        "现在在哪个项目",
        "现在在什么项目",
        "当前项目是什么",
        "确认一下当前项目",
        "报一下当前项目",
    ):
        return "/状态"
    if any(
        phrase in stripped
        for phrase in ("哪个项目", "什么项目", "当前项目", "现在在哪个")
    ) and any(
        hint in stripped
        for hint in ("当前", "现在", "哪个", "什么", "确认", "报", "我是")
    ):
        if any(
            verb in stripped
            for verb in ("读", "读取", "列出", "写", "删", "委派", "检查", "README", "文件")
        ):
            return None
        return "/状态"
    if any(
        phrase in stripped
        for phrase in ("有哪些项目", "项目列表", "哪些workspace", "几个项目")
    ):
        return "/项目"
    if any(
        phrase in stripped
        for phrase in ("总览", "全部项目状态", "所有项目", "项目仪表盘", "dashboard")
    ):
        return "/总览"
    return None


def _normalize_new_session_request(text: str) -> str | None:
    """Allow ``/新对话`` with trailing natural-language hints."""
    stripped = (text or "").strip()
    if stripped == "/新对话" or stripped.startswith("/新对话"):
        return "/新对话"
    return None


def _normalize_memo_request(text: str) -> str | None:
    """Map natural phrases about memos to ``/备忘``."""
    stripped = (text or "").strip().rstrip("。.!！?？")
    if not stripped:
        return None
    if stripped in ("查看备忘", "我的备忘", "备忘录", "备忘列表", "看看备忘",
                    "有什么备忘", "备忘有哪些"):
        return "/备忘"
    return None


def _normalize_contacts_request(text: str) -> str | None:
    """Map natural phrases about contacts to ``/通讯录``."""
    stripped = (text or "").strip().rstrip("。.!！?？")
    if not stripped:
        return None
    if stripped in ("通讯录", "联系人", "我的通讯录", "查看通讯录", "联系人列表"):
        return "/通讯录"
    return None


def _normalize_expense_request(text: str) -> str | None:
    """Map natural phrases about expenses to ``/记账``."""
    stripped = (text or "").strip().rstrip("。.!！?？")
    if not stripped:
        return None
    if stripped in ("记账", "账单", "看看账单", "这个月花了多少", "本月支出",
                    "本月账单", "收支", "我的账单"):
        return "/记账"
    return None


def _normalize_habits_request(text: str) -> str | None:
    """Map natural phrases about habits to ``/打卡``."""
    stripped = (text or "").strip().rstrip("。.!！?？")
    if not stripped:
        return None
    if stripped in ("打卡", "习惯", "今日打卡", "我的习惯", "习惯打卡",
                    "看看打卡", "打卡情况"):
        return "/打卡"
    return None


def _normalize_detail_request(text: str) -> str | None:
    """Map WeChat-friendly「详细」to ``/详细`` without requiring a slash prefix."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    lower = stripped.lower()
    if "报错" in stripped or "错误信息" in stripped:
        return None
    for marker, cmd in (("/详细", "/详细"), ("/detail", "/detail")):
        idx = lower.find(marker)
        if idx >= 0:
            rest = stripped[idx + len(marker) :].strip().rstrip("，,。.!！?？")
            return f"{cmd} {rest}".strip() if rest else cmd
    detail_aliases = {
        "/详细",
        "/detail",
        "详细",
        "detail",
        "查看详细",
        "看详细",
        "完整报告",
        "详细信息",
        "查看详细信息",
        "看一下详细",
        "看一下详细信息",
        "我要看一下详细信息",
        "看详细信息",
    }
    if lower in detail_aliases or stripped in detail_aliases:
        return "/详细"
    for prefix in ("详细", "详细信息", "看一下详细"):
        if stripped.startswith(prefix) and len(stripped) > len(prefix):
            rest = stripped[len(prefix) :].strip()
            if rest.startswith("信息"):
                rest = rest[2:].strip()
            if rest:
                return "/详细 " + rest
    if stripped.startswith("详细 "):
        return "/详细 " + stripped[3:].strip()
    if lower.startswith("detail "):
        return "/detail " + stripped[7:].strip()
    return None


def _gateway_run_callbacks():
    from butler.core.agent_loop import LoopCallbacks
    from butler.gateway.outbound_bridge import get_current_bridge

    bridge = get_current_bridge()
    if bridge is None:
        return None

    def _on_stream_delta(chunk: str) -> None:
        bridge.append_stream_preview(chunk)

    return LoopCallbacks(
        on_tool_start=bridge.on_tool_start,
        on_tool_complete=bridge.on_tool_complete,
        on_stream_delta=_on_stream_delta,
    )


def _is_prequeue_interrupt_command(text: str) -> bool:
    stripped = (text or "").strip().lower()
    if not stripped.startswith("/"):
        return False
    cmd = stripped.split(maxsplit=1)[0]
    return cmd in {
        "/stop",
        "/停止",
        "/中断",
        "/cancel-loop",
        "/停止循环",
        "/stoploop",
    }


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _is_sessionless_command(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return False
    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower()
    return cmd in {
        "/projects",
        "/项目",
        "/switch",
        "/切换",
        "/model",
        "/模型",
        "/status",
        "/状态",
        "/health",
        "/诊断",
        "/doctor",
        "/steer",
        "/指引",
        "/queue",
        "/stop",
        "/停止",
        "/中断",
        "/cancel-loop",
        "/continue",
        "/继续",
        "/确认",
        "/approve",
        "/取消",
        "/cancel",
        "/new",
        "/新对话",
        "/detail",
        "/详细",
        "/plan",
        "/计划",
        "/规划",
        "/执行",
        "/exit-plan",
        "/退出规划",
        "/todos",
        "/待办",
        "/tasks",
        "/memo",
        "/备忘",
        "/通讯录",
        "/contacts",
        "/记账",
        "/expense",
        "/打卡",
        "/habits",
        "/任务",
        "/config",
        "/配置",
        "/帮助",
        "/help",
        "/导出",
        "/export",
        "/export-session",
        "/导出会话",
        "/回滚",
        "/transcript-revert",
        "/revert-transcript",
        "/批准一次",
        "/approve-once",
        "/始终允许",
        "/always-allow",
        "/权限",
        "/permissions",
        "/workflow",
        "/工作流",
        "/定时",
        "/runtime",
        "/定时任务",
        "/运行",
        "/run-job",
        "/运行任务",
        "/批准运行",
        "/approve-run",
        "/批准任务",
        "/记忆待审",
        "/pending-memory",
        "/待审记忆",
        "/记忆图谱",
        "/memory-graph",
        "/三元组",
        "/批准记忆",
        "/approve-memory",
        "/拒绝记忆",
        "/reject-memory",
        "/拒绝",
        "/批准",
        "/开发状态",
        "/dev-status",
        "/开发验收",
        "/dev-smoke",
        "/git",
        "/测试",
        "/test",
        "/构建",
        "/build",
        "/项目概况",
        "/project-dashboard",
    }


def _tool_audit_summary(session_key: str) -> dict[str, Any]:
    try:
        from butler.tools.registry import get_tool_audit_events
    except Exception:
        return {"total": 0, "failed": 0, "codes": []}
    events = get_tool_audit_events(limit=50, session_key=session_key)
    failed = [event for event in events if not event.get("ok", False)]
    codes = sorted({str(event.get("code")) for event in failed if event.get("code")})
    return {"total": len(events), "failed": len(failed), "codes": codes}


def _reset_tool_audit_events(session_key: str | None = None) -> None:
    try:
        from butler.tools.registry import reset_tool_audit_events
    except Exception:
        return
    reset_tool_audit_events(session_key)


_WELCOMED_SESSIONS: set[str] = set()

_WELCOME_TEXT = """Hi，我是你的 Butler 管家！首次对话，快速了解我的能力：

项目管理：/项目 | /切换 | /总览
代码操作：读写文件、搜索、委派开发/审核
记忆系统：跨会话记住你的偏好和决策
提醒功能：设置定时提醒（如「提醒我明天开会」）
待办管理：/待办（会话级）| /项目待办（持久）
诊断运维：/诊断 | /状态

推荐先试试这 3 个命令：
  /项目   — 查看和管理你的项目
  /帮助   — 查看所有可用命令
  /诊断   — 系统健康检查

如有任何问题，直接跟我说就好！"""


def _maybe_welcome_prefix(session_key: str) -> str:
    """Return welcome text for first-time sessions, empty string otherwise."""
    if os.getenv("BUTLER_ONBOARDING_WELCOME", "1").strip() == "0":
        return ""
    if session_key in _WELCOMED_SESSIONS:
        return ""
    _WELCOMED_SESSIONS.add(session_key)

    marker = Path(os.getenv("BUTLER_HOME", "~/.butler")).expanduser() / "welcomed_sessions.txt"
    try:
        if marker.is_file():
            known = set(marker.read_text(encoding="utf-8").strip().splitlines())
            if session_key in known:
                return ""
        marker.parent.mkdir(parents=True, exist_ok=True)
        with open(marker, "a", encoding="utf-8") as f:
            f.write(session_key + "\n")
    except Exception as exc:
        logger.debug("maybe welcome prefix skipped: %s", exc)
    return _WELCOME_TEXT


def _build_project_overview(orchestrator: Any, session_key: str) -> str:
    """Build a multi-project dashboard for /总览."""
    pm = orchestrator.project_manager
    projects = pm.list_projects()
    if not projects:
        return "暂无项目。"

    current = pm.resolve_active_project_name(session_key=session_key)
    lines = ["📋 项目总览", ""]

    for p in sorted(projects, key=lambda x: x.name):
        mark = "▸ " if p.name == current else "  "
        header = f"{mark}{p.name}"
        if p.name == current:
            header += "（当前）"

        sub: list[str] = []
        workspace = getattr(p, "workspace", None)

        if workspace:
            from pathlib import Path

            ws = Path(workspace)
            todos_path = ws / ".butler" / "todos.json"
            if todos_path.is_file():
                try:
                    import json as _json
                    todos_data = _json.loads(todos_path.read_text(encoding="utf-8"))
                    pending = [t for t in todos_data if t.get("status") == "pending"]
                    if pending:
                        sub.append(f"待办 {len(pending)} 项")
                except Exception as exc:
                    logger.debug("build project overview skipped: %s", exc)
            jobs_path = ws / "runtime" / "jobs.yaml"
            if jobs_path.is_file():
                try:
                    from butler.runtime.service import list_jobs_status, runtime_enabled

                    if runtime_enabled():
                        job_rows = list_jobs_status(p.name)
                        if job_rows:
                            sub.append(f"定时任务 {len(job_rows)} 个")
                except Exception as exc:
                    logger.debug("build project overview skipped: %s", exc)
            summary_path = ws / ".butler" / "session_summary.json"
            if summary_path.is_file():
                try:
                    import json as _json
                    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
                    turns = summary.get("turns", 0)
                    if turns:
                        sub.append(f"上次会话 {turns} 轮")
                except Exception as exc:
                    logger.debug("build project overview skipped: %s", exc)
        pack = getattr(p, "pack", "") or ""
        ptype = p.type or ""
        desc_parts = [ptype]
        if pack:
            desc_parts.append(f"pack={pack}")
        if sub:
            desc_parts.append("｜".join(sub))

        lines.append(f"{header}  [{', '.join(desc_parts)}]")
        if p.description:
            lines.append(f"    {p.description[:60]}")

    lines.append("")
    lines.append("提醒：")
    try:
        from butler.tools.reminder import _load_all

        reminders = [r for r in _load_all() if r.get("status") == "pending"]
        if reminders:
            lines.append(f"  待触发提醒 {len(reminders)} 个")
            for r in reminders[:3]:
                lines.append(f"    · {r.get('due_human', '')} — {r.get('message', '')[:40]}")
        else:
            lines.append("  无待触发提醒")
    except Exception:
        lines.append("  提醒系统不可用")

    return "\n".join(lines)


def _inject_previous_session_summary(loop: "AgentLoop", project: Any) -> None:
    """Inject previous session summary into a new AgentLoop for context continuity."""
    try:
        from butler.env_parse import env_truthy

        if not env_truthy("BUTLER_SESSION_SUMMARY", default=True):
            return
        if project is None:
            return
        workspace = getattr(project, "workspace", None)
        if not workspace:
            return

        import json
        from pathlib import Path

        summary_path = Path(workspace) / ".butler" / "session_summary.json"
        if not summary_path.is_file():
            return

        raw = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return

        parts: list[str] = []
        proj_name = raw.get("project", "")
        turns = raw.get("turns", 0)
        if proj_name:
            parts.append(f"上次会话项目：{proj_name}，{turns} 轮对话")
        for field, label in [
            ("persona", "用户偏好"),
            ("preference", "设置变更"),
            ("experience", "经验记录"),
        ]:
            items = raw.get(field) or []
            if items:
                parts.append(f"{label}：" + "；".join(str(i) for i in items[:5]))

        if not parts:
            return

        context = "[上次会话摘要]\n" + "\n".join(parts) + "\n[/上次会话摘要]"
        if hasattr(loop, "_messages"):
            loop._messages.append({"role": "system", "content": context})
            logger.debug("Injected previous session summary (%d chars)", len(context))
    except Exception as exc:
        logger.debug("Session summary injection skipped: %s", exc)


def _on_gateway_session_removed(session_key: str) -> None:
    _reset_tool_audit_events(session_key)
    try:
        from butler.mcp.registry_hook import disconnect_mcp_session

        disconnect_mcp_session(session_key)
    except Exception as exc:
        logger.debug("on gateway session removed skipped: %s", exc)
