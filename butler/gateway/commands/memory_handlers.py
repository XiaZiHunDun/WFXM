"""Gateway slash commands for project MEMORY.md pending queue."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from butler.gateway.commands.memory_handlers_ops import (
    approve_all_owner_pending,
    approve_owner_pending_index,
    current_project_name,
    experience_entry_count,
    list_owner_pending,
    owner_pending_lines,
    profile_entry_count,
    project_memory_bullet_total,
    reject_all_owner_pending,
    reject_owner_pending_index,
)
from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


def _project_memory(orchestrator: "ButlerOrchestrator"):
    orchestrator._reload_project_memory()
    return orchestrator._project_memory


def format_pending_memory_list(orchestrator: "ButlerOrchestrator") -> str:
    lines: list[str] = []
    owner_lines = owner_pending_lines()
    if owner_lines:
        lines.extend(owner_lines)
        lines.append("")

    pmem = _project_memory(orchestrator)
    if pmem is None and not lines:
        return "当前没有待批准的记忆（Pending 队列为空）。"
    if pmem is not None:
        pending = pmem.markdown.list_pending()
        if pending:
            lines.append("项目 MEMORY 待批准（Pending 队列）:")
            lines.append("")
            for i, item in enumerate(pending, start=1):
                tgt = item.get("target") or "Decisions"
                body = (item.get("content") or "").strip()
                if len(body) > 120:
                    body = body[:117] + "..."
                lines.append(f"P{i}. → {tgt} | {body}")
            lines.append("")
    if not lines:
        return "当前没有待批准的记忆（Pending 队列为空）。"
    lines.append("批准: /批准记忆 <序号> 或 P<序号>（项目）  或  /批准记忆 全部")
    lines.append("拒绝: /拒绝记忆 <序号>  或  /拒绝记忆 全部")
    return "\n".join(lines)


def format_memory_triplet_graph(orchestrator: "ButlerOrchestrator") -> str:
    bm = getattr(orchestrator, "butler_memory", None)
    if bm is None:
        return "Butler 记忆未初始化。"
    tri = bm.triplet_index() if hasattr(bm, "triplet_index") else None
    if tri is None:
        return (
            "记忆图谱（三元组仅展示）需要开启语义索引："
            "在 .env 设置 BUTLER_SEMANTIC_MEMORY=1 后执行 memory-reindex。"
        )
    proj_name = current_project_name(orchestrator)
    total = tri.count(project=proj_name or None)
    lines = [
        "记忆图谱（三元组仅展示，不参与检索排序）",
        f"条目: {total} 条"
        + (f"（含全局 + 项目 {proj_name}）" if proj_name else "（全局）"),
        "",
        tri.format_display(project=proj_name or None, limit=12),
        "",
        "写入 MEMORY / 经验 / 画像后自动从「A 采用 B」类句式提取。",
    ]
    return "\n".join(lines)


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
    """Handle /记忆待审, /批准记忆, /拒绝记忆, /记忆图谱. Returns None if cmd not recognized.

    Sprint 11 SEC-11-2: /批准记忆 路径加 owner gate（永久污染 MEMORY.md）。
    """
    if cmd in ("/记忆图谱", "/memory-graph", "/三元组"):
        return format_memory_triplet_graph(orchestrator)

    if cmd in ("/记忆待审", "/pending-memory", "/待审记忆"):
        return format_pending_memory_list(orchestrator)

    if cmd in ("/拒绝记忆", "/reject-memory", "/拒绝"):
        return _handle_reject_pending(orchestrator, arg)

    if cmd not in ("/批准记忆", "/approve-memory", "/批准"):
        return None

    if not cli and not is_gateway_owner(
        platform=platform, external_id=external_id, session_key=session_key
    ):
        return owner_required_message()

    return _handle_approve_pending(orchestrator, arg)


def _handle_approve_pending(orchestrator: "ButlerOrchestrator", arg: str) -> str:
    key = (arg or "").strip().lower()
    if key in ("全部", "all", "*"):
        bm = getattr(orchestrator, "butler_memory", None)
        owner_count = approve_all_owner_pending(bm) if bm is not None else 0
        proj_count = 0
        pmem = _project_memory(orchestrator)
        if pmem is not None:
            pending_before = pmem.markdown.list_pending()
            proj_count = pmem.markdown.approve_all()
            _sync_vectors_after_approve(orchestrator, pending_before[:proj_count])
        return f"已批准所有者记忆 {owner_count} 条、项目记忆 {proj_count} 条。"

    if not arg.strip():
        return "用法: /批准记忆 <序号> 或 P<序号>（项目）  或  /批准记忆 全部\n先发送 /记忆待审 查看列表。"

    raw = arg.strip()
    if raw.upper().startswith("P"):
        return _approve_project_pending(orchestrator, raw[1:])

    try:
        idx = int(raw) - 1
    except ValueError:
        return "序号必须是数字。例: /批准记忆 1  或  /批准记忆 P1"

    bm = getattr(orchestrator, "butler_memory", None)
    owner_pending = list_owner_pending()
    if owner_pending and 0 <= idx < len(owner_pending):
        if bm is None:
            return "Butler 记忆未初始化。"
        result = approve_owner_pending_index(idx, bm)
        if result and result.get("ok"):
            scope = owner_pending[idx].get("scope", "?")
            return f"已批准所有者记忆第 {idx + 1} 条（{scope}）。"
        if result:
            return f"批准失败: {result.get('error', 'unknown')}"

    return _approve_project_pending(orchestrator, raw)


def _approve_project_pending(orchestrator: "ButlerOrchestrator", arg: str) -> str:
    pmem = _project_memory(orchestrator)
    if pmem is None:
        return "请先 /切换 到已选项目，或批准所有者记忆序号（无 P 前缀）。"

    try:
        idx = int(arg.strip()) - 1
    except ValueError:
        return "项目序号必须是数字。例: /批准记忆 P1"

    pending = pmem.markdown.list_pending()
    if not pending:
        return "没有待批准的项目记忆条目。"
    if not (0 <= idx < len(pending)):
        return f"项目序号超出范围（P1–P{len(pending)}）。"

    if pmem.markdown.approve_pending(idx):
        item = pending[idx]
        _sync_vectors_after_approve(orchestrator, [item])
        return f"已批准项目记忆 P{idx + 1}，写入章节: {item.get('target', 'Decisions')}"
    return "批准失败（条目可能已被处理）。"


def _handle_reject_pending(orchestrator: "ButlerOrchestrator", arg: str) -> str:
    key = (arg or "").strip().lower()
    if key in ("全部", "all", "*"):
        owner_count = reject_all_owner_pending()
        proj_count = 0
        pmem = _project_memory(orchestrator)
        if pmem is not None:
            pending_before = pmem.markdown.list_pending()
            proj_count = pmem.markdown.reject_all_pending()
            _sync_vectors_after_reject(orchestrator, pending_before[:proj_count])
        return f"已拒绝所有者记忆 {owner_count} 条、项目记忆 {proj_count} 条。"

    if not arg.strip():
        return "用法: /拒绝记忆 <序号> 或 P<序号>（项目）  或  /拒绝记忆 全部\n先发送 /记忆待审 查看列表。"

    raw = arg.strip()
    if raw.upper().startswith("P"):
        return _reject_project_pending(orchestrator, raw[1:])

    try:
        idx = int(raw) - 1
    except ValueError:
        return "序号必须是数字。例: /拒绝记忆 1  或  /拒绝记忆 P1"

    owner_pending = list_owner_pending()
    if owner_pending and 0 <= idx < len(owner_pending):
        if reject_owner_pending_index(idx):
            return f"已拒绝所有者记忆第 {idx + 1} 条。"
        return "拒绝失败（条目可能已被处理）。"

    return _reject_project_pending(orchestrator, raw)


def _reject_project_pending(orchestrator: "ButlerOrchestrator", arg: str) -> str:
    pmem = _project_memory(orchestrator)
    if pmem is None:
        return "请先 /切换 到已选项目。"

    try:
        idx = int(arg.strip()) - 1
    except ValueError:
        return "项目序号必须是数字。例: /拒绝记忆 P1"

    pending = pmem.markdown.list_pending()
    if not pending:
        return "没有待拒绝的项目记忆条目。"
    if not (0 <= idx < len(pending)):
        return f"项目序号超出范围（P1–P{len(pending)}）。"

    item = pending[idx]
    if pmem.markdown.reject_pending(idx):
        _sync_vectors_after_reject(orchestrator, [item])
        return f"已拒绝项目记忆 P{idx + 1}，已从 Pending 移除。"
    return "拒绝失败（条目可能已被处理）。"


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
    from butler.memory.vector_sync_telemetry import record_vector_sync

    record_vector_sync("project_pending", project=proj.name)


def _sync_vectors_after_reject(
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
    from butler.memory.semantic_project import invalidate_pending_vector

    for item in items:
        body = (item.get("content") or "").strip()
        if body:
            invalidate_pending_vector(sem, proj.name, body)


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

    pmem = _project_memory(orchestrator)
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
    "format_pending_memory_list",
    "format_memory_triplet_graph",
    "handle_memory_pending_command",
]
