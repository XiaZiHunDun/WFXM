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
    """Explicit dependency container for Butler services.
    
    Replaces scattered singletons with managed lifecycle.
    Supports override/reset for testing.
    """

    def __init__(self) -> None:
        self._project_manager = LazyInstance(self._create_project_manager)
        self._settings = LazyInstance(self._create_settings)
        self._session_monitor = LazyInstance(self._create_session_monitor)
        self._memory_metrics = LazyInstance(self._create_memory_metrics)
        self._events_sink = LazyInstance(self._create_events_sink)
        self._event_store = LazyInstance(self._create_event_store)
        self._conversation_store = LazyInstance(self._create_conversation_store)
        self._knowledge_graph = LazyInstance(self._create_knowledge_graph)
        self._hybrid_retriever = LazyInstance(self._create_hybrid_retriever)
        self._experience_store = LazyInstance(self._create_experience_store)

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

    def event_store(self):
        return self._event_store.get()

    def override_event_store(self, value) -> None:
        self._event_store.override(value)

    def conversation_store(self):
        return self._conversation_store.get()

    def override_conversation_store(self, value) -> None:
        self._conversation_store.override(value)

    def knowledge_graph(self):
        return self._knowledge_graph.get()

    def override_knowledge_graph(self, value) -> None:
        self._knowledge_graph.override(value)

    def hybrid_retriever(self):
        return self._hybrid_retriever.get()

    def override_hybrid_retriever(self, value) -> None:
        self._hybrid_retriever.override(value)

    def experience_store(self):
        return self._experience_store.get()

    def override_experience_store(self, value) -> None:
        self._experience_store.override(value)

    def reset_all(self) -> None:
        """Reset all services (for testing)."""
        self._project_manager.reset()
        self._settings.reset()
        self._session_monitor.reset()
        self._memory_metrics.reset()
        self._events_sink.reset()
        self._event_store.reset()
        self._conversation_store.reset()
        self._knowledge_graph.reset()
        self._hybrid_retriever.reset()
        self._experience_store.reset()

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

    def _create_event_store(self):
        from butler.core.event_store import create_default_event_store

        return create_default_event_store()

    def _create_conversation_store(self):
        from butler.memory.conversation_store import ConversationStore

        return ConversationStore()

    def _create_knowledge_graph(self):
        from butler.memory.knowledge_graph import KnowledgeGraph

        return KnowledgeGraph()

    def _create_hybrid_retriever(self):
        from butler.memory.hybrid_retriever import HybridRetriever

        return HybridRetriever()

    def _create_experience_store(self):
        from butler.memory.experience.store import ExperienceStore

        return ExperienceStore()


container = ServiceContainer()
"""Global service container instance."""

__all__ = ["ServiceContainer", "LazyInstance", "container"]