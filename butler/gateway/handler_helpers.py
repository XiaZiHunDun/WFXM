"""Gateway message handler helper functions.

Extracted from message_handler.py. Contains text normalization,
command classification, project overview building, and session
management utilities.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from butler.tools._file_cache import read_json_cached

if TYPE_CHECKING:
    from butler.core.agent_loop import AgentLoop

logger = logging.getLogger(__name__)

# EXT-2 / 外部 SaaS：含这些词时不走 Butler 多项目 /总览、/项目 归一化
_EXTERNAL_INTEGRATION_MARKERS = (
    "todoist",
    "notion",
    "linear",
    "trello",
    "asana",
)


def _mentions_external_integrations(text: str) -> bool:
    lower = (text or "").strip().lower()
    return any(marker in lower for marker in _EXTERNAL_INTEGRATION_MARKERS)


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
        if _mentions_external_integrations(stripped):
            return None
        return "/项目"
    if any(
        phrase in stripped
        for phrase in ("总览", "全部项目状态", "所有项目", "项目仪表盘", "dashboard")
    ):
        if _mentions_external_integrations(stripped):
            return None
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


def apply_auto_continue_rewrite(session_key: str, text: str) -> str | None:
    """Sprint 16 TST-10-5 第八批: 抽自 message_handler.py:426-433 pre-dispatch rewriter.

    如果用户输入是 continue marker 且有 fresh pending, 返回改写后的 text (供后续 dispatch);
    否则返 None (text 不变). 异常吞掉 + logger.debug, 与原 inline try/except 行为一致.

    注意: 这是 text rewriter, **不**是 slash dispatch handler — 返回值是 "新 text" 而非 reply 字符串.
    """
    try:
        from butler.core.auto_continue import resolve_auto_continue_user_message

        return resolve_auto_continue_user_message(session_key, text)
    except Exception as exc:
        logger.debug("Auto continue resolve skipped: %s", exc)
        return None


def _env_int(name: str, default: int) -> int:
    from butler.env_parse import int_env

    return int_env(name, default)


def _env_float(name: str, default: float) -> float:
    from butler.env_parse import float_env

    return float_env(name, default)


def _is_sessionless_command(text: str) -> bool:
    """Decide whether *text* names a sessionless slash command.

    Sprint 18-4 D CRITICAL-2: 真源 = command_registry. 已注册命令(含 aliases)
    立即识别, 动态注册的新命令零漂移. 未注册命令返 False (降级到 session
    队列后 LLM, 与原硬编码 set 中"未注册"成员的实际行为对齐 — 那些命令
    在 dispatch 失败后同样 fallback 到 LLM).

    行为变化: 之前 27 项已注册但不在 set 的命令 (新 dispatch 命令) 现在
    sessionless, 立即响应; 之前 45 项在 set 但未注册的命令现在等 session
    队列, 仅延迟差异 (最终 LLM 接收, 功能不变).
    """
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return False
    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower()
    if not cmd:
        return False
    from butler.gateway.command_registry import lookup

    return lookup(cmd) is not None


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
_WELCOMED_LOCK = threading.Lock()

_WELCOME_TEXT = """Hi，我是你的 Butler 管家！首次对话，快速了解我的能力：

项目管理：/项目 | /切换 | /总览
代码操作：读写文件、搜索、委派开发/审核
记忆系统：跨会话记住你的偏好和决策
提醒功能：设置定时提醒（如「提醒我明天开会」）
待办管理：/待办（会话级）| /项目待办（持久）
诊断运维：/诊断（会话全量）| /doctor（仅安全审计）| /状态

推荐先试试这 3 个命令：
  /项目   — 查看和管理你的项目
  /帮助   — 查看所有可用命令
  /诊断   — 系统健康检查

如有任何问题，直接跟我说就好！"""

# User already asked for identity/capabilities — LLM reply supersedes static welcome.
_WELCOME_SUPERSEDED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"介绍.{0,8}(自己|你)|自我介绍", re.I),
    re.compile(r"你是谁|你叫什么|什么名字|who\s+are\s+you", re.I),
    re.compile(r"(可以|能|会).{0,12}(干什么|做什么|帮我|什么)", re.I),
    re.compile(r"(什么|哪些).{0,8}(能力|功能|命令)", re.I),
    re.compile(r"^/?帮助$", re.I),
)


def _user_turn_supersedes_welcome(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    return any(pat.search(text) for pat in _WELCOME_SUPERSEDED_PATTERNS)


def _mark_session_welcomed(session_key: str) -> None:
    """Persist first-contact marker without emitting welcome text."""
    with _WELCOMED_LOCK:
        if session_key in _WELCOMED_SESSIONS:
            return
        _WELCOMED_SESSIONS.add(session_key)

    marker = Path(os.getenv("BUTLER_HOME", "~/.butler")).expanduser() / "welcomed_sessions.txt"
    try:
        if marker.is_file():
            known = set(marker.read_text(encoding="utf-8").strip().splitlines())
            if session_key in known:
                return
        marker.parent.mkdir(parents=True, exist_ok=True)
        with open(marker, "a", encoding="utf-8") as f:
            f.write(session_key + "\n")
    except Exception as exc:
        logger.debug("mark session welcomed skipped: %s", exc)


def _maybe_welcome_prefix(session_key: str, user_text: str = "") -> str:
    """Return welcome text for first-time sessions, empty string otherwise."""
    from butler.defaults.env_defaults import ONBOARDING_WELCOME_DEFAULT

    if os.getenv("BUTLER_ONBOARDING_WELCOME", ONBOARDING_WELCOME_DEFAULT).strip() == "0":
        return ""
    if _user_turn_supersedes_welcome(user_text):
        _mark_session_welcomed(session_key)
        return ""
    with _WELCOMED_LOCK:
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


def _safe_overview_sub(fn: Callable[[], str | None], label: str) -> str | None:
    """Run a `_build_project_overview` sub-info extractor; swallow + log on failure.

    Sprint 22-7 QUAL-21-D-1: 3 sub-info paths (todos / jobs / summary)
    used the same try/except + logger.debug("...skipped: %s", exc)
    skeleton. Centralising the wrapper keeps the per-path code focused
    on data extraction and makes future sub-infos cheap to add.
    """
    try:
        return fn()
    except Exception as exc:
        logger.debug("build project overview skipped (%s): %s", label, exc)
        return None


def _todos_subinfo(ws: Path) -> str | None:
    todos_path = ws / ".butler" / "todos.json"
    if not todos_path.is_file():
        return None
    todos_data = read_json_cached(todos_path)
    if not isinstance(todos_data, list):
        todos_data = []
    pending = [t for t in todos_data if t.get("status") == "pending"]
    if pending:
        return f"待办 {len(pending)} 项"
    return None


def _jobs_subinfo(ws: Path, project_name: str) -> str | None:
    jobs_path = ws / "runtime" / "jobs.yaml"
    if not jobs_path.is_file():
        return None
    from butler.runtime.service import list_jobs_status, runtime_enabled

    if not runtime_enabled():
        return None
    job_rows = list_jobs_status(project_name)
    if job_rows:
        return f"定时任务 {len(job_rows)} 个"
    return None


def _summary_subinfo(ws: Path) -> str | None:
    summary_path = ws / ".butler" / "session_summary.json"
    if not summary_path.is_file():
        return None
    summary = read_json_cached(summary_path)
    if not isinstance(summary, dict):
        summary = {}
    turns = summary.get("turns", 0)
    if turns:
        return f"上次会话 {turns} 轮"
    return None


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
            for label, msg in (
                ("todos", _safe_overview_sub(lambda: _todos_subinfo(ws), "todos")),
                ("jobs", _safe_overview_sub(lambda: _jobs_subinfo(ws, p.name), "jobs")),
                ("summary", _safe_overview_sub(lambda: _summary_subinfo(ws), "summary")),
            ):
                if msg:
                    sub.append(msg)
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

        from pathlib import Path

        summary_path = Path(workspace) / ".butler" / "session_summary.json"
        if not summary_path.is_file():
            return

        raw = read_json_cached(summary_path)
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
