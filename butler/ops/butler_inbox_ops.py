"""Best-effort inbox snapshot collectors (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.tools.project_todos import _load
from butler.tools.reminder import _load_all
from butler.memory.experience_mining import load_pending
from butler.core.compaction_status import derive_compaction_status, format_compaction_status_line
from butler.gateway.message_queue import pending_count
from butler.contracts.workflow_gate_registry import get_workflow_gate
from butler.core.session_tool_index import list_session_read_files
from butler.ops.owner_quality_surface import format_b9_owner_line, format_mcp_owner_line
from butler.ops.owner_trust_surface import format_trust_owner_line


def project_todos_info_safe(workspace: Path) -> tuple[int, list[str]]:
    def _run() -> tuple[int, list[str]]:

        items = _load(workspace)
        open_items = [t for t in items if t.get("status") in ("pending", "in_progress")]
        samples = [
            str(t.get("content") or "")[:48]
            for t in open_items[:3]
            if str(t.get("content") or "").strip()
        ]
        return len(open_items), samples

    result = safe_best_effort(_run, label="butler_inbox.project_todos", default=(0, []))
    if isinstance(result, tuple) and len(result) == 2:
        n, samples = result
        return int(n), list(samples) if isinstance(samples, list) else []
    return 0, []


def reminders_info_safe() -> tuple[int, list[str]]:
    def _run() -> tuple[int, list[str]]:

        pending = [r for r in _load_all() if r.get("status") == "pending"]
        samples = [
            f"{r.get('due_human', '')} {str(r.get('message') or '')[:36]}".strip()
            for r in pending[:3]
        ]
        return len(pending), samples

    result = safe_best_effort(_run, label="butler_inbox.reminders", default=(0, []))
    if isinstance(result, tuple) and len(result) == 2:
        return int(result[0]), list(result[1])
    return 0, []


def memory_pending_count_safe(orchestrator: Any) -> int:
    def _run() -> int:
        orchestrator._reload_project_memory()
        pmem = orchestrator._project_memory
        if pmem is None:
            return 0
        return len(pmem.markdown.list_pending())

    result = safe_best_effort(_run, label="butler_inbox.memory_pending", default=0)
    return int(result) if isinstance(result, int) else 0


def experience_pending_count_safe() -> int:
    def _run() -> int:

        return len(load_pending())

    result = safe_best_effort(_run, label="butler_inbox.experience_pending", default=0)
    return int(result) if isinstance(result, int) else 0


def compaction_line_safe(health: dict | None) -> str:
    def _run() -> str:

        h = health or {}
        if derive_compaction_status(h) == "none":
            return ""
        return format_compaction_status_line(h)

    result = safe_best_effort(_run, label="butler_inbox.compaction", default="")
    return result if isinstance(result, str) else ""


def queue_pending_count_safe(session_key: str) -> int:
    def _run() -> int:

        return int(pending_count(session_key))

    result = safe_best_effort(_run, label="butler_inbox.queue", default=0)
    return int(result) if isinstance(result, int) else 0


def workflow_gate_hint_safe(session_key: str) -> str:
    def _run() -> str:

        gate = get_workflow_gate()
        if gate.has_pending_gate(session_key):
            return str(gate.format_pending_hint(session_key) or "")
        return ""

    result = safe_best_effort(_run, label="butler_inbox.workflow_gate", default="")
    return result if isinstance(result, str) else ""


def session_reads_count_safe(session_key: str, workspace: Any) -> int:
    def _run() -> int:

        return len(list_session_read_files(session_key, workspace=workspace, limit=50))

    result = safe_best_effort(_run, label="butler_inbox.session_reads", default=0)
    return int(result) if isinstance(result, int) else 0


def quality_surface_lines_safe(
    session_key: str,
    workspace: Path | None,
) -> tuple[str, str]:
    def _run() -> tuple[str, str]:

        return (
            format_mcp_owner_line(session_key, workspace=workspace),
            format_b9_owner_line(),
        )

    result = safe_best_effort(_run, label="butler_inbox.quality_surface", default=("", ""))
    if isinstance(result, tuple) and len(result) == 2:
        return str(result[0]), str(result[1])
    return "", ""


def trust_line_safe(orchestrator: Any, session_key: str, health: dict | None) -> str:
    def _run() -> str:

        return str(format_trust_owner_line(orchestrator, session_key, health=health) or "")

    result = safe_best_effort(_run, label="butler_inbox.trust", default="")
    return result if isinstance(result, str) else ""
