"""Delegate job carrier types (no delegate_job / async_delegate import cycle)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DelegatePushTarget:
    adapter: Any
    chat_id: str
    loop: Any


@dataclass
class DelegateJob:
    agent: Any
    orch: Any
    user_msg: str
    raw_user_msg: str
    role: str
    task: str
    session_key: str
    child_session_key: str
    task_id: str
    category_meta: dict[str, Any] = field(default_factory=dict)
    bridge: Any | None = None
    push_target: DelegatePushTarget | None = None
    use_async_push: bool = False


__all__ = ["DelegateJob", "DelegatePushTarget"]
