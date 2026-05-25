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
_current_workflow_step: ContextVar[str] = ContextVar(
    "butler_current_workflow_step",
    default="",
)
_workflow_var_pool: ContextVar[object | None] = ContextVar(
    "butler_workflow_var_pool",
    default=None,
)


def get_current_orchestrator() -> "ButlerOrchestrator | None":
    """Return the orchestrator bound to the current AgentLoop/tool turn."""
    return _current_orchestrator.get()


def get_current_session_key() -> str:
    """Return the external session key bound to the current turn, if any."""
    return _current_session_key.get()


def get_current_workflow_step() -> str:
    """Active workflow step id during DAG node execution (for step-level permissions)."""
    return str(_current_workflow_step.get() or "").strip()


def get_workflow_var_pool() -> object | None:
    return _workflow_var_pool.get()


@contextmanager
def use_workflow_var_pool(pool: object | None) -> Iterator[None]:
    token = _workflow_var_pool.set(pool)
    try:
        yield
    finally:
        _workflow_var_pool.reset(token)


@contextmanager
def use_workflow_step(step_id: str) -> Iterator[None]:
    """Bind workflow step id for tool permission checks in orchestrator nodes."""
    token = _current_workflow_step.set(str(step_id or "").strip())
    try:
        yield
    finally:
        _current_workflow_step.reset(token)


@contextmanager
def use_execution_context(
    orchestrator: "ButlerOrchestrator | None" = None,
    *,
    session_key: str = "",
) -> Iterator[None]:
    """Temporarily bind orchestrator and/or session key for nested tools and delegates."""
    orch_token = None
    if orchestrator is not None:
        orch_token = _current_orchestrator.set(orchestrator)
    session_token = _current_session_key.set(session_key)
    try:
        yield
    finally:
        _current_session_key.reset(session_token)
        if orch_token is not None:
            _current_orchestrator.reset(orch_token)


def get_audit_session_key(*, fallback: str = "unscoped") -> str:
    """Session key for tool audit when no external session is bound."""
    key = str(get_current_session_key() or "").strip()
    if key:
        return key
    if get_current_orchestrator() is not None:
        return ""
    return fallback
