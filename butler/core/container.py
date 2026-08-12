"""Explicit dependency container — replaces scattered singletons with managed lifecycle.

Usage:
    from butler.core.container import container

    # Get services
    pm = container.project_manager()
    settings = container.settings()

    # Override for testing
    container.override_project_manager(mock_pm)

    # Validate dependencies (detect cycles)
    container.validate_dependencies()
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Generic, Set, TypeVar

from butler.configuration.settings import ButlerSettings
from butler.contracts.events import NullEventsSink
from butler.core.effects.result import Err, Ok, Result
from butler.core.event_store import create_default_event_store
from butler.memory.conversation_store import ConversationStore
from butler.memory.experience.store import ExperienceStore
from butler.memory.hybrid_retriever import HybridRetriever
from butler.memory.knowledge_graph import KnowledgeGraph
from butler.memory.memory_metrics import MemoryMetricsCollector
from butler.project.manager import ProjectManager
from butler.session.session_monitor import SessionMonitor

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


class DependencyCycleError(Exception):
    """Raised when a circular dependency is detected in the service container."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(
            f"Circular dependency detected: {' → '.join(cycle)}"
        )


class DependencyCycleResult(Err[None, DependencyCycleError]):
    """Err variant for dependency cycle detection."""


class ServiceContainer:
    """Explicit dependency container for Butler services.

    Replaces scattered singletons with managed lifecycle.
    Supports override/reset for testing.
    """

    def __init__(self) -> None:
        self._project_manager: LazyInstance[ProjectManager] = LazyInstance(self._create_project_manager)
        self._settings: LazyInstance[ButlerSettings] = LazyInstance(self._create_settings)
        self._session_monitor: LazyInstance[SessionMonitor] = LazyInstance(self._create_session_monitor)
        self._memory_metrics: LazyInstance[MemoryMetricsCollector] = LazyInstance(self._create_memory_metrics)
        self._events_sink: LazyInstance[NullEventsSink] = LazyInstance(self._create_events_sink)
        self._event_store: LazyInstance[Any] = LazyInstance(self._create_event_store)
        self._conversation_store: LazyInstance[ConversationStore] = LazyInstance(self._create_conversation_store)
        self._knowledge_graph: LazyInstance[KnowledgeGraph] = LazyInstance(self._create_knowledge_graph)
        self._hybrid_retriever: LazyInstance[HybridRetriever] = LazyInstance(self._create_hybrid_retriever)
        self._experience_store: LazyInstance[ExperienceStore] = LazyInstance(self._create_experience_store)

    def project_manager(self) -> ProjectManager:
        return self._project_manager.get()

    def override_project_manager(self, value: ProjectManager) -> None:
        self._project_manager.override(value)

    def settings(self) -> ButlerSettings:
        return self._settings.get()

    def override_settings(self, value: ButlerSettings) -> None:
        self._settings.override(value)

    def session_monitor(self) -> SessionMonitor:
        return self._session_monitor.get()

    def override_session_monitor(self, value: SessionMonitor) -> None:
        self._session_monitor.override(value)

    def memory_metrics(self) -> MemoryMetricsCollector:
        return self._memory_metrics.get()

    def override_memory_metrics(self, value: MemoryMetricsCollector) -> None:
        self._memory_metrics.override(value)

    def events_sink(self) -> NullEventsSink:
        return self._events_sink.get()

    def override_events_sink(self, value: NullEventsSink) -> None:
        self._events_sink.override(value)

    def event_store(self):
        return self._event_store.get()

    def override_event_store(self, value) -> None:
        self._event_store.override(value)

    def conversation_store(self) -> ConversationStore:
        return self._conversation_store.get()

    def override_conversation_store(self, value: ConversationStore) -> None:
        self._conversation_store.override(value)

    def knowledge_graph(self) -> KnowledgeGraph:
        return self._knowledge_graph.get()

    def override_knowledge_graph(self, value: KnowledgeGraph) -> None:
        self._knowledge_graph.override(value)

    def hybrid_retriever(self) -> HybridRetriever:
        return self._hybrid_retriever.get()

    def override_hybrid_retriever(self, value: HybridRetriever) -> None:
        self._hybrid_retriever.override(value)

    def experience_store(self) -> ExperienceStore:
        return self._experience_store.get()

    def override_experience_store(self, value: ExperienceStore) -> None:
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
        return ProjectManager()

    def _create_settings(self):
        return ButlerSettings()

    def _create_session_monitor(self):
        return SessionMonitor()

    def _create_memory_metrics(self):
        return MemoryMetricsCollector()

    def _create_events_sink(self):
        return NullEventsSink()

    def _create_event_store(self):
        return create_default_event_store()

    def _create_conversation_store(self):
        return ConversationStore()

    def _create_knowledge_graph(self):
        return KnowledgeGraph()

    def _create_hybrid_retriever(self):
        return HybridRetriever()

    def _create_experience_store(self):
        return ExperienceStore()

    def validate_dependencies(self) -> Result[None, DependencyCycleError]:
        """Validate the dependency graph for circular dependencies.

        Based on opencode's Layer dependency graph validation pattern.
        Detects cycles at registration time before they cause runtime errors.

        Returns:
            Result[None, DependencyCycleError]: Ok(None) if no cycles, Err(DependencyCycleError) if cycle detected.
        """
        # Define the dependency graph (service -> list of dependencies)
        # Note: This is a manual declaration for static analysis
        dependency_graph = {
            "project_manager": [],
            "settings": [],
            "session_monitor": [],
            "memory_metrics": [],
            "events_sink": [],
            "event_store": [],
            "conversation_store": [],
            "knowledge_graph": [],
            "hybrid_retriever": [],
            "experience_store": [],
        }

        # Perform cycle detection using DFS
        def dfs(node: str, path: list[str], visited: Set[str]) -> Result[None, DependencyCycleError]:
            if node in visited:
                if node in path:
                    # Found a cycle
                    cycle_start = path.index(node)
                    cycle = path[cycle_start:] + [node]
                    return Err(DependencyCycleError(cycle))
                return Ok(None)

            visited.add(node)
            path.append(node)

            for dependency in dependency_graph.get(node, []):
                result = dfs(dependency, path, visited)
                if result.is_err():
                    return result

            path.pop()
            return Ok(None)

        # Check all nodes
        visited: Set[str] = set()
        for service in dependency_graph:
            if service not in visited:
                result = dfs(service, [], visited)
                if result.is_err():
                    return result

        logger.debug("Dependency graph validation passed: no cycles detected")
        return Ok(None)


container = ServiceContainer()
"""Global service container instance."""

__all__ = ["ServiceContainer", "LazyInstance", "DependencyCycleError", "DependencyCycleResult", "container", "Result", "Ok", "Err"]
