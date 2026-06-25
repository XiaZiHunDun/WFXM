"""Owner brief / inbox — aggregate actionable items for WeChat."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class InboxSnapshot:
    project_name: str = ""
    workspace: str = ""
    project_todos_open: int = 0
    project_todo_samples: list[str] = field(default_factory=list)
    reminders_pending: int = 0
    reminder_samples: list[str] = field(default_factory=list)
    memory_pending: int = 0
    experience_pending: int = 0
    queue_pending: int = 0
    workflow_gate: str = ""
    session_reads: int = 0
    compaction_line: str = ""
    mcp_line: str = ""
    b9_line: str = ""
    trust_line: str = ""


def _project_todos_info(workspace: Path) -> tuple[int, list[str]]:
    try:
        from butler.tools.project_todos import _load

        items = _load(workspace)
        open_items = [
            t for t in items if t.get("status") in ("pending", "in_progress")
        ]
        samples = [
            str(t.get("content") or "")[:48]
            for t in open_items[:3]
            if str(t.get("content") or "").strip()
        ]
        return len(open_items), samples
    except Exception as exc:
        logger.debug("inbox project todos skipped: %s", exc)
        return 0, []


def _reminders_info() -> tuple[int, list[str]]:
    try:
        from butler.tools.reminder import _load_all

        pending = [r for r in _load_all() if r.get("status") == "pending"]
        samples = [
            f"{r.get('due_human', '')} {str(r.get('message') or '')[:36]}".strip()
            for r in pending[:3]
        ]
        return len(pending), samples
    except Exception as exc:
        logger.debug("inbox reminders skipped: %s", exc)
        return 0, []


def _memory_pending_count(orchestrator: Any) -> int:
    try:
        orchestrator._reload_project_memory()
        pmem = orchestrator._project_memory
        if pmem is None:
            return 0
        return len(pmem.markdown.list_pending())
    except Exception as exc:
        logger.debug("inbox memory pending skipped: %s", exc)
        return 0


def _experience_pending_count() -> int:
    try:
        from butler.memory.experience_mining import load_pending

        return len(load_pending())
    except Exception as exc:
        logger.debug("inbox experience pending skipped: %s", exc)
        return 0


def _compaction_line(health: dict | None) -> str:
    try:
        from butler.core.compaction_status import (
            derive_compaction_status,
            format_compaction_status_line,
        )

        h = health or {}
        if derive_compaction_status(h) == "none":
            return ""
        return format_compaction_status_line(h)
    except Exception as exc:
        logger.debug("inbox compaction skipped: %s", exc)
        return ""


def collect_inbox_snapshot(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict | None = None,
) -> InboxSnapshot:
    sk = str(session_key or "").strip()
    snap = InboxSnapshot()
    pm = orchestrator.project_manager
    proj = pm.get_current(session_key=sk)
    if proj is not None:
        snap.project_name = str(getattr(proj, "name", "") or "")
        ws = getattr(proj, "workspace", None)
        if ws:
            snap.workspace = str(Path(ws).resolve())
            open_n, samples = _project_todos_info(Path(ws))
            snap.project_todos_open = open_n
            snap.project_todo_samples = samples
    else:
        snap.project_name = pm.resolve_active_project_name(session_key=sk)

    snap.reminders_pending, snap.reminder_samples = _reminders_info()
    snap.memory_pending = _memory_pending_count(orchestrator)
    snap.experience_pending = _experience_pending_count()

    try:
        from butler.gateway.message_queue import pending_count

        snap.queue_pending = pending_count(sk)
    except Exception as exc:
        logger.debug("inbox queue skipped: %s", exc)

    try:
        from butler.human_gate import format_pending_hint, has_pending_gate

        if has_pending_gate(sk):
            snap.workflow_gate = format_pending_hint(sk)
    except Exception as exc:
        logger.debug("inbox workflow gate skipped: %s", exc)

    try:
        from butler.core.session_tool_index import list_session_read_files

        ws = getattr(proj, "workspace", None) if proj else None
        snap.session_reads = len(
            list_session_read_files(sk, workspace=ws, limit=50)
        )
    except Exception as exc:
        logger.debug("inbox session reads skipped: %s", exc)

    snap.compaction_line = _compaction_line(health)

    try:
        from butler.ops.owner_quality_surface import (
            format_b9_owner_line,
            format_mcp_owner_line,
        )

        ws_path = Path(snap.workspace) if snap.workspace else None
        snap.mcp_line = format_mcp_owner_line(sk, workspace=ws_path)
        snap.b9_line = format_b9_owner_line()
    except Exception as exc:
        logger.debug("inbox quality surface skipped: %s", exc)

    try:
        from butler.ops.owner_trust_surface import format_trust_owner_line

        snap.trust_line = format_trust_owner_line(orchestrator, sk, health=health)
    except Exception as exc:
        logger.debug("inbox trust surface skipped: %s", exc)

    return snap


def _action_count(snap: InboxSnapshot) -> int:
    n = 0
    if snap.project_todos_open:
        n += 1
    if snap.reminders_pending:
        n += 1
    if snap.memory_pending:
        n += 1
    if snap.experience_pending:
        n += 1
    if snap.queue_pending:
        n += 1
    if snap.workflow_gate:
        n += 1
    return n


def format_owner_brief(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict | None = None,
) -> str:
    """Owner /简报 — fixed blocks: 待办 · 队列 · 门控 · 昨夜 job (PROD-P1-02)."""
    from butler.gateway.owner_surface import (
        _pending_delegate_line,
        format_owner_status_header,
    )
    from butler.ops.owner_brief_blocks import format_overnight_jobs_lines

    snap = collect_inbox_snapshot(orchestrator, session_key, health=health)
    lines = ["📬 管家简报", ""]
    lines.extend(format_owner_status_header(orchestrator, session_key, health=health))
    if snap.project_name:
        lines.append(f"项目：{snap.project_name}")
    lines.append("")

    # ── 1. 待办 ──
    lines.append("【待办】")
    todo_lines: list[str] = []
    if snap.project_todos_open:
        todo_lines.append(f"  项目待办 {snap.project_todos_open} 项")
        for item in snap.project_todo_samples[:3]:
            todo_lines.append(f"    - {item}")
        if snap.project_todos_open > 3:
            todo_lines.append("    … → /项目待办")
    if snap.reminders_pending:
        todo_lines.append(f"  提醒 {snap.reminders_pending} 个待触发")
        for item in snap.reminder_samples[:2]:
            todo_lines.append(f"    - {item}")
    if snap.memory_pending:
        todo_lines.append(f"  记忆待审 {snap.memory_pending} 条 → /记忆待审")
    if snap.experience_pending:
        todo_lines.append(f"  经验待审 {snap.experience_pending} 条")
    delegate = _pending_delegate_line(session_key)
    if delegate:
        todo_lines.append(f"  {delegate}")
    if not todo_lines:
        todo_lines.append("  无待办 ✅")
    lines.extend(todo_lines)

    # ── 2. 队列 ──
    lines.append("")
    lines.append("【队列】")
    if snap.queue_pending:
        lines.append(f"  入站待发 {snap.queue_pending} 条 → /queue")
    else:
        lines.append("  入站队列空 ✅")

    # ── 3. 门控 ──
    lines.append("")
    lines.append("【门控】")
    if snap.workflow_gate:
        lines.append(f"  {snap.workflow_gate[:120]}")
    else:
        lines.append("  无待确认工作流 ✅")

    # ── 4. 昨夜 job ──
    lines.append("")
    lines.append("【昨夜 job】")
    lines.extend(format_overnight_jobs_lines(snap.project_name))

    lines.append("")
    lines.append("更多：/inbox · /今日 · /高级")
    return "\n".join(lines)


def format_owner_inbox(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict | None = None,
) -> str:
    """Detailed inbox for /inbox."""
    snap = collect_inbox_snapshot(orchestrator, session_key, health=health)
    lines = ["📥 管家收件箱", ""]
    if snap.project_name:
        lines.append(f"▸ 当前项目：{snap.project_name}")
    if snap.workspace:
        lines.append(f"  工作区：`{snap.workspace}`")
    lines.append("")

    lines.append("## 项目待办")
    if snap.project_todos_open:
        lines.append(f"未完成 {snap.project_todos_open} 项：")
        for item in snap.project_todo_samples:
            lines.append(f"  · {item}")
        if snap.project_todos_open > len(snap.project_todo_samples):
            extra = snap.project_todos_open - len(snap.project_todo_samples)
            lines.append(f"  … 另有 {extra} 项（/项目待办）")
    else:
        lines.append("  无未完成项")

    lines.append("")
    lines.append("## 提醒")
    if snap.reminders_pending:
        lines.append(f"待触发 {snap.reminders_pending} 个：")
        for item in snap.reminder_samples:
            lines.append(f"  · {item}")
    else:
        lines.append("  无待触发提醒")

    lines.append("")
    lines.append("## 待审批")
    mem_parts: list[str] = []
    if snap.memory_pending:
        mem_parts.append(f"记忆 {snap.memory_pending} 条（/记忆待审）")
    if snap.experience_pending:
        mem_parts.append(f"经验挖掘 {snap.experience_pending} 条")
    lines.append("  " + (" · ".join(mem_parts) if mem_parts else "无"))

    lines.append("")
    lines.append("## 通道")
    if snap.queue_pending:
        lines.append(f"  入站队列待发：{snap.queue_pending} 条")
    else:
        lines.append("  入站队列：空")
    if snap.workflow_gate:
        lines.append(f"  门控：{snap.workflow_gate}")

    lines.append("")
    lines.append("## 本轮会话")
    if snap.session_reads:
        lines.append(f"  已 read_file：{snap.session_reads} 个（/本轮已读）")
    else:
        lines.append("  尚未 read_file")
    if snap.compaction_line:
        lines.append(f"  {snap.compaction_line}")

    lines.append("")
    from butler.ops.owner_quality_surface import format_mcp_owner_block

    lines.extend(
        format_mcp_owner_block(
            session_key,
            workspace=Path(snap.workspace) if snap.workspace else None,
        )
    )

    lines.append("")
    lines.append("## 委派质量")
    if snap.b9_line:
        lines.append(f"  {snap.b9_line}")
    else:
        lines.append("  （未记录）")
    lines.append("  详情：/委派质量")

    lines.append("")
    from butler.ops.owner_trust_surface import format_trust_owner_block

    lines.extend(format_trust_owner_block(orchestrator, session_key, health=health))

    return "\n".join(lines)


__all__ = [
    "InboxSnapshot",
    "collect_inbox_snapshot",
    "format_owner_brief",
    "format_owner_inbox",
]
