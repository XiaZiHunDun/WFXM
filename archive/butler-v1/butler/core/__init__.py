"""Core module - Butler, ProjectManager, and shared agent state."""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from butler.executors.agent_runner import AgentResult


class _ProgressHandler:
    """Thread-local-ish holder for the active progress callback.
    Set by Butler/adapters before delegating to agents.
    """
    _handler: Callable | None = None

    def set(self, handler: Callable | None) -> None:
        self._handler = handler

    def get(self) -> Callable | None:
        return self._handler

    def clear(self) -> None:
        self._handler = None


class _LastReportCache:
    """Caches the most recent AgentResult for /detail access."""
    _result: Any = None

    def set(self, result: Any) -> None:
        self._result = result

    def get(self) -> Any:
        return self._result

    def clear(self) -> None:
        self._result = None


_progress_handler = _ProgressHandler()
_last_report_cache = _LastReportCache()


from butler.core.butler import Butler  # noqa: E402
from butler.core.project_manager import ProjectManager, project_manager  # noqa: E402

__all__ = ["Butler", "ProjectManager", "project_manager", "_progress_handler", "_last_report_cache"]
