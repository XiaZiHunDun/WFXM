"""Mutable carrier for delegate phase orchestration (ENG-2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DelegateRunState:
    """Mutable carrier passed through phase helpers of ``_tool_delegate_task``.

    All fields start empty; each phase populates the fields it owns.
    Using a small carrier avoids passing 10+ parameters between helpers
    and keeps the host function readable.
    """

    # --- input -----------------------------------------------------------
    role: str = ""
    task: str = ""
    context: str = ""
    category: str = ""
    depth: int = 0
    original_context: str = ""

    # --- resolved during phases ------------------------------------------
    category_meta: dict[str, Any] = field(default_factory=dict)
    bridge: Any = None
    orch: Any = None
    project: Any = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    delegated_tools: list[dict[str, Any]] = field(default_factory=list)
    agent: Any = None
    user_msg: str = ""
    raw_user_msg: str = ""
    memory_sync_user_msg: str = ""
    session_key: str = ""
    task_id: str = ""
    child_session_key: str = ""

    # --- control flow ----------------------------------------------------
    # When non-empty, the host should return this JSON string immediately
    # (depth exceeded, concurrency exceeded, async dispatch result).
    early_return: str = ""
    # Sync-run result lives here when ``_run_subagent_loop`` returns None.
    sync_result: Any = None


__all__ = ["DelegateRunState"]
