"""Explicit dependency container — replaces scattered singletons with managed lifecycle.

Usage:
    from butler.core.container import container

    # Get services
    pm = container.project_manager()
    settings = container.settings()

    # Override for testing
    container.override_project_manager(mock_pm)
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Generic, Optional, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LazyInstance(Generic[T]):
    """Lazy-initialized singleton with override support."""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._instance: T | None = None
        self._override: T | None = None

    def get(self) -> T:
        if self._override is not None:
            return self._override
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    def override(self, value: T) -> None:
        self._override = value

    def reset(self) -> None:
        self._instance = None
        self._override = None


class ServiceContainer:
    """Explicit dependency container for Butler services."""

    def __init__(self) -> None:
        self._project_manager = LazyInstance(self._create_project_manager)
        self._settings = LazyInstance(self._create_settings)
        self._session_monitor = LazyInstance(self._create_session_monitor)
        self._memory_metrics = LazyInstance(self._create_memory_metrics)
        self._events_sink = LazyInstance(self._create_events_sink)

    def project_manager(self):
        return self._project_manager.get()

    def override_project_manager(self, value) -> None:
        self._project_manager.override(value)

    def settings(self):
        return self._settings.get()

    def override_settings(self, value) -> None:
        self._settings.override(value)

    def session_monitor(self):
        return self._session_monitor.get()

    def override_session_monitor(self, value) -> None:
        self._session_monitor.override(value)

    def memory_metrics(self):
        return self._memory_metrics.get()

    def override_memory_metrics(self, value) -> None:
        self._memory_metrics.override(value)

    def events_sink(self):
        return self._events_sink.get()

    def override_events_sink(self, value) -> None:
        self._events_sink.override(value)

    def reset_all(self) -> None:
        """Reset all services (for testing)."""
        self._project_manager.reset()
        self._settings.reset()
        self._session_monitor.reset()
        self._memory_metrics.reset()
        self._events_sink.reset()

    def _create_project_manager(self):
        from butler.project.manager import ProjectManager

        return ProjectManager()

    def _create_settings(self):
        from butler.configuration.settings import ButlerSettings

        return ButlerSettings()

    def _create_session_monitor(self):
        from butler.session.session_monitor import SessionMonitor

        return SessionMonitor()

    def _create_memory_metrics(self):
        from butler.memory.memory_metrics import MemoryMetricsCollector

        return MemoryMetricsCollector()

    def _create_events_sink(self):
        from butler.contracts.events import NullEventsSink

        return NullEventsSink()


container = ServiceContainer()
"""Global service container instance."""

__all__ = ["ServiceContainer", "LazyInstance", "container"]