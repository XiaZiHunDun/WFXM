"""Gateway slash commands for project MEMORY.md pending queue."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


def _project_memory(orchestrator: "ButlerOrchestrator"):
    orchestrator._reload_project_memory()
    return orchestrator._project_memory


def format_pending_memory_list(orchestrator: "ButlerOrchestrator") -> str:
    pmem = _project_memory(orchestrator)
    if pmem is None:
        return "请先 /切换 到已选项目，再查看待审记忆。"
    pending = pmem.markdown.list_pending()
    if not pending:
        return "当前项目没有待批准的记忆（Pending 队列为空）。"
    lines = ["待批准记忆（写入 project MEMORY.md Pending 队列）:", ""]
    for i, item in enumerate(pending, start=1):
        tgt = item.get("target") or "Decisions"
        body = (item.get("content") or "").strip()
        if len(body) > 120:
            body = body[:117] + "..."
        lines.append(f"{i}. → {tgt} | {body}")
    lines.append("")
    lines.append("批准: /批准记忆 <序号>  或  /批准记忆 全部")
    return "\n".join(lines)


def handle_memory_pending_command(
    orchestrator: "ButlerOrchestrator",
    cmd: str,
    arg: str,
) -> Optional[str]:
    """Handle /记忆待审 and /批准记忆. Returns None if cmd not recognized."""
    if cmd in ("/记忆待审", "/pending-memory", "/待审记忆"):
        return format_pending_memory_list(orchestrator)

    if cmd not in ("/批准记忆", "/approve-memory", "/批准"):
        return None

    pmem = _project_memory(orchestrator)
    if pmem is None:
        return "请先 /切换 到已选项目。"

    key = (arg or "").strip().lower()
    if key in ("全部", "all", "*"):
        pending_before = pmem.markdown.list_pending()
        count = pmem.markdown.approve_all()
        _sync_vectors_after_approve(orchestrator, pending_before[:count])
        return f"已批准 {count} 条待审记忆，并移入对应章节。"

    if not arg.strip():
        return "用法: /批准记忆 <序号>  或  /批准记忆 全部\n先发送 /记忆待审 查看列表。"

    try:
        idx = int(arg.strip()) - 1
    except ValueError:
        return "序号必须是数字。例: /批准记忆 1"

    pending = pmem.markdown.list_pending()
    if not pending:
        return "没有待批准条目。"
    if not (0 <= idx < len(pending)):
        return f"序号超出范围（1–{len(pending)}）。"

    if pmem.markdown.approve_pending(idx):
        item = pending[idx]
        _sync_vectors_after_approve(orchestrator, [item])
        return f"已批准第 {idx + 1} 条，写入章节: {item.get('target', 'Decisions')}"
    return "批准失败（条目可能已被处理）。"


def _sync_vectors_after_approve(
    orchestrator: "ButlerOrchestrator",
    items: list[dict[str, str]],
) -> None:
    if not items:
        return
    bm = getattr(orchestrator, "butler_memory", None)
    sem = getattr(bm, "semantic", None) if bm is not None else None
    if sem is None:
        return
    proj = orchestrator.project_manager.get_current()
    if proj is None:
        return
    from butler.memory.semantic_project import (
        index_project_memory_bullet,
        invalidate_pending_vector,
    )

    for item in items:
        body = (item.get("content") or "").strip()
        tgt = (item.get("target") or "Decisions").strip() or "Decisions"
        if not body:
            continue
        invalidate_pending_vector(sem, proj.name, body)
        index_project_memory_bullet(sem, proj.name, tgt, body)


__all__ = [
    "format_pending_memory_list",
    "handle_memory_pending_command",
]
