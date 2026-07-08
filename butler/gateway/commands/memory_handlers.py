"""Gateway slash commands for project MEMORY.md pending queue."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from butler.gateway.owner_gate import is_gateway_owner, owner_required_message
from butler.memory.pending_command_ops import (
    experience_entry_count,
    profile_entry_count,
    project_memory_bullet_total,
)
from butler.memory.pending_handlers import (
    format_memory_triplet_graph,
    format_pending_memory_list,
    handle_memory_pending_command as _handle_memory_pending_core,
)

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


def handle_memory_pending_command(
    orchestrator: "ButlerOrchestrator",
    cmd: str,
    arg: str,
    *,
    platform: str = "",
    external_id: str | None = None,
    session_key: str = "",
    cli: bool = False,
) -> Optional[str]:
    """Handle /记忆待审, /批准记忆, /拒绝记忆, /记忆图谱. Returns None if cmd not recognized."""
    if cmd not in ("/批准记忆", "/approve-memory", "/批准"):
        return _handle_memory_pending_core(orchestrator, cmd, arg)

    if not cli and not is_gateway_owner(
        platform=platform, external_id=external_id, session_key=session_key
    ):
        return str(owner_required_message())

    return _handle_memory_pending_core(orchestrator, cmd, arg)


def format_memory_status(orchestrator: "ButlerOrchestrator", *, session_key: str = "") -> str:
    """Show memory system status: profile, experience, project entries, vector index."""
    lines = ["记忆系统状态", ""]

    bm = getattr(orchestrator, "butler_memory", None)
    if bm is None:
        lines.append("Butler Memory: 未初始化")
    else:
        profile = getattr(bm, "profile", None)
        if profile is not None:
            count = profile_entry_count(profile)
            if count is None:
                lines.append("Profile: 读取失败")
            else:
                lines.append(f"Profile 条目数: {count}")

        experience = getattr(bm, "experience", None)
        if experience is not None:
            count = experience_entry_count(experience)
            if count is None:
                lines.append("Experience: 读取失败")
            else:
                lines.append(f"Experience 条目数: {count}")

        semantic = getattr(bm, "semantic", None)
        if semantic is not None:
            lines.append("向量索引: 已初始化")
        else:
            lines.append("向量索引: 未初始化")

    orchestrator._reload_project_memory()
    pmem = orchestrator._project_memory
    if pmem is not None:
        pending = pmem.markdown.list_pending()
        lines.append(f"项目 MEMORY Pending: {len(pending)} 条")
        total = project_memory_bullet_total(pmem)
        if total is not None:
            lines.append(f"项目 MEMORY 条目: {total} 条")
    else:
        lines.append("项目 MEMORY: 未选择项目")

    import time

    lines.append(f"最后检查: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


__all__ = [
    "format_memory_status",
    "format_memory_triplet_graph",
    "format_pending_memory_list",
    "handle_memory_pending_command",
]
