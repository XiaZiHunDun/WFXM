"""Base executor interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class BaseExecutor(ABC):
    """Base class for task executors."""

    name: str = "base"

    @abstractmethod
    async def execute(
        self,
        project_name: str,
        task: str,
        on_progress: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute a task and return the result."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this executor is available."""
        ...
