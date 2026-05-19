"""Current Butler execution context shared across tool and delegate paths."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


_current_orchestrator: ContextVar["ButlerOrchestrator | None"] = ContextVar(
    "butler_current_orchestrator",
    default=None,
)
_current_session_key: ContextVar[str] = ContextVar(
    "butler_current_session_key",
    default="",
)


def get_current_orchestrator() -> "ButlerOrchestrator | None":
    """Return the orchestrator bound to the current AgentLoop/tool turn."""
    return _current_orchestrator.get()


def get_current_session_key() -> str:
    """Return the external session key bound to the current turn, if any."""
    return _current_session_key.get()


@contextmanager
def use_execution_context(
    orchestrator: "ButlerOrchestrator",
    *,
    session_key: str = "",
) -> Iterator[None]:
    """Temporarily bind a Butler orchestrator for nested tools and delegates."""
    orch_token = _current_orchestrator.set(orchestrator)
    session_token = _current_session_key.set(session_key)
    try:
        yield
    finally:
        _current_session_key.reset(session_token)
        _current_orchestrator.reset(orch_token)
