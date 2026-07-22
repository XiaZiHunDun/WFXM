"""Integration tests for ServiceContainer and EventStore."""

from __future__ import annotations

import pytest
from pathlib import Path

from butler.core.container import ServiceContainer, container, LazyInstance
from butler.core.event_store import EventStore, StoredEvent


class TestLazyInstance:
    def test_lazy_initialization(self):
        counter = [0]

        def factory():
            counter[0] += 1
            return counter[0]

        lazy = LazyInstance(factory)

        assert counter[0] == 0
        assert lazy.get() == 1
        assert counter[0] == 1
        assert lazy.get() == 1
        assert counter[0] == 1

    def test_override(self):
        def factory():
            return "original"

        lazy = LazyInstance(factory)
        assert lazy.get() == "original"

        lazy.override("overridden")
        assert lazy.get() == "overridden"

    def test_reset(self):
        counter = [0]

        def factory():
            counter[0] += 1
            return counter[0]

        lazy = LazyInstance(factory)
        lazy.get()
        lazy.get()
        assert counter[0] == 1

        lazy.reset()
        lazy.get()
        assert counter[0] == 2


class TestServiceContainer:
    def test_project_manager(self):
        container.reset_all()
        pm = container.project_manager()
        assert pm is not None

    def test_settings(self):
        container.reset_all()
        settings = container.settings()
        assert settings is not None

    def test_session_monitor(self):
        container.reset_all()
        monitor = container.session_monitor()
        assert monitor is not None

    def test_memory_metrics(self):
        container.reset_all()
        metrics = container.memory_metrics()
        assert metrics is not None

    def test_override_project_manager(self):
        container.reset_all()

        class MockProjectManager:
            def __init__(self):
                self.mocked = True

        mock_pm = MockProjectManager()
        container.override_project_manager(mock_pm)

        pm = container.project_manager()
        assert pm is mock_pm
        assert pm.mocked is True

    def test_override_settings(self):
        container.reset_all()

        class MockSettings:
            pass

        mock_settings = MockSettings()
        container.override_settings(mock_settings)

        settings = container.settings()
        assert settings is mock_settings

    def test_reset_all_clears_overrides(self):
        container.reset_all()

        class MockProjectManager:
            pass

        mock_pm = MockProjectManager()
        container.override_project_manager(mock_pm)
        assert container.project_manager() is mock_pm

        container.reset_all()
        assert container.project_manager() is not mock_pm


class TestContainerEventStoreIntegration:
    def test_events_sink_with_event_store(self, tmp_path: Path):
        container.reset_all()

        db_path = tmp_path / "container_events.db"
        event_store = EventStore(db_path)

        container.override_events_sink(event_store)

        sink = container.events_sink()
        assert isinstance(sink, EventStore)

        event = StoredEvent(
            event_id="container-test-001",
            event_type="CONTAINER_TEST",
            payload={"test": "integration"},
            session_key="container-session",
            timestamp=1234567890.0,
        )
        sink.store(event)

        retrieved = sink.query_by_session("container-session")
        assert len(retrieved) == 1
        assert retrieved[0].event_type == "CONTAINER_TEST"

    def test_multiple_resolves_return_same_instance(self):
        container.reset_all()

        pm1 = container.project_manager()
        pm2 = container.project_manager()

        assert pm1 is pm2