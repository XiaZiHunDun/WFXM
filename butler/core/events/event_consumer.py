"""Event consumer for real-time monitoring and analytics.

Subscribes to the event bus and provides:
  - Real-time event processing
  - Metrics collection
  - Audit logging
  - Session tracking

Inspired by CQRS pattern - events are consumed asynchronously for read models.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from butler.core.events.event_store import (
    DomainEvent,
    EnhancedEventBus,
    get_global_event_bus,
    get_global_event_store,
)

logger = logging.getLogger(__name__)


class EventConsumer:
    """Base class for event consumers."""

    def __init__(self, event_types: Optional[Set[str]] = None) -> None:
        self._event_types = event_types or set()
        self._bus: Optional[EnhancedEventBus] = None
        self._subscribed = False

    def subscribe(self, bus: Optional[EnhancedEventBus] = None) -> None:
        """Subscribe to the event bus."""
        if self._subscribed:
            return
        self._bus = bus or get_global_event_bus()
        if self._event_types:
            for event_type in self._event_types:
                self._bus.subscribe(event_type, self._handle_event)
        else:
            self._bus.subscribe("*", self._handle_event)
        self._subscribed = True
        logger.info("EventConsumer subscribed (types: %s)", self._event_types or "all")

    def unsubscribe(self) -> None:
        """Unsubscribe from the event bus."""
        if not self._subscribed or not self._bus:
            return
        if self._event_types:
            for event_type in self._event_types:
                self._bus.unsubscribe(event_type, self._handle_event)
        else:
            self._bus.unsubscribe("*", self._handle_event)
        self._subscribed = False

    def _handle_event(self, event: DomainEvent) -> None:
        """Handle an incoming event."""
        raise NotImplementedError


class EventMetricsCollector(EventConsumer):
    """Collects metrics from domain events for monitoring."""

    def __init__(self) -> None:
        super().__init__()
        self._metrics: Dict[str, Any] = {
            "event_counts": defaultdict(int),
            "session_counts": defaultdict(int),
            "llm_api_calls": [],
            "tool_calls": [],
            "memory_syncs": [],
            "errors": [],
        }
        self._lock = threading.Lock()
        self._start_time = time.time()

    def _handle_event(self, event: DomainEvent) -> None:
        """Process events and collect metrics."""
        with self._lock:
            self._metrics["event_counts"][event.event_type] += 1

            if event.session_key:
                self._metrics["session_counts"][event.session_key] += 1

            if event.event_type == "LLMApiCall":
                self._metrics["llm_api_calls"].append({
                    "timestamp": event.timestamp,
                    "session_key": event.session_key,
                    "data": event.data,
                })

            elif event.event_type == "ToolCallCompleted":
                is_error = event.data.get("is_error", False)
                self._metrics["tool_calls"].append({
                    "timestamp": event.timestamp,
                    "session_key": event.session_key,
                    "tool_name": event.data.get("tool_name", ""),
                    "is_error": is_error,
                })
                if is_error:
                    self._metrics["errors"].append({
                        "timestamp": event.timestamp,
                        "event_type": event.event_type,
                        "session_key": event.session_key,
                        "error": event.data.get("error", ""),
                    })

            elif event.event_type == "MemorySyncCompleted":
                self._metrics["memory_syncs"].append({
                    "timestamp": event.timestamp,
                    "session_key": event.session_key,
                    "success_count": event.data.get("success_count", 0),
                    "error_count": event.data.get("error_count", 0),
                })

            elif event.data.get("is_error"):
                self._metrics["errors"].append({
                    "timestamp": event.timestamp,
                    "event_type": event.event_type,
                    "session_key": event.session_key,
                    "error": event.data.get("error", ""),
                })

    def get_metrics(self) -> Dict[str, Any]:
        """Return collected metrics."""
        with self._lock:
            uptime = time.time() - self._start_time
            return {
                "uptime_seconds": uptime,
                "event_counts": dict(self._metrics["event_counts"]),
                "session_counts": dict(self._metrics["session_counts"]),
                "total_events": sum(self._metrics["event_counts"].values()),
                "total_sessions": len(self._metrics["session_counts"]),
                "llm_api_call_count": len(self._metrics["llm_api_calls"]),
                "tool_call_count": len(self._metrics["tool_calls"]),
                "memory_sync_count": len(self._metrics["memory_syncs"]),
                "error_count": len(self._metrics["errors"]),
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._metrics = {
                "event_counts": defaultdict(int),
                "session_counts": defaultdict(int),
                "llm_api_calls": [],
                "tool_calls": [],
                "memory_syncs": [],
                "errors": [],
            }
            self._start_time = time.time()


class EventAuditLogger(EventConsumer):
    """Logs events for audit trail purposes."""

    def __init__(self, max_history: int = 1000) -> None:
        super().__init__()
        self._history: List[Dict[str, Any]] = []
        self._max_history = max_history
        self._lock = threading.Lock()

    def _handle_event(self, event: DomainEvent) -> None:
        """Log events for audit trail."""
        audit_entry = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "session_key": event.session_key,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "data": event.data,
            "version": event.version,
        }
        with self._lock:
            self._history.append(audit_entry)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent audit entries."""
        with self._lock:
            return list(self._history[-limit:])

    def search_by_session(self, session_key: str) -> List[Dict[str, Any]]:
        """Search events by session key."""
        with self._lock:
            return [
                entry for entry in self._history
                if entry.get("session_key") == session_key
            ]

    def search_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """Search events by type."""
        with self._lock:
            return [
                entry for entry in self._history
                if entry.get("event_type") == event_type
            ]

    def reset(self) -> None:
        """Reset audit history."""
        with self._lock:
            self._history = []


class SessionActivityTracker(EventConsumer):
    """Tracks session activity for monitoring."""

    def __init__(self) -> None:
        super().__init__()
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _handle_event(self, event: DomainEvent) -> None:
        """Update session activity based on events."""
        if not event.session_key:
            return

        with self._lock:
            if event.session_key not in self._sessions:
                self._sessions[event.session_key] = {
                    "first_event": event.timestamp,
                    "last_event": event.timestamp,
                    "event_count": 0,
                    "llm_calls": 0,
                    "tool_calls": 0,
                    "errors": 0,
                }

            session = self._sessions[event.session_key]
            session["last_event"] = event.timestamp
            session["event_count"] += 1

            if event.event_type == "LLMApiCall":
                session["llm_calls"] += 1
            elif event.event_type == "ToolCallCompleted":
                session["tool_calls"] += 1
                if event.data.get("is_error"):
                    session["errors"] += 1

    def get_session_activity(self, session_key: str) -> Optional[Dict[str, Any]]:
        """Get activity for a specific session."""
        with self._lock:
            return self._sessions.get(session_key)

    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get activity for all sessions."""
        with self._lock:
            return dict(self._sessions)

    def get_active_sessions(self, minutes: int = 5) -> Dict[str, Dict[str, Any]]:
        """Get sessions active in the last N minutes."""
        cutoff = time.time() - (minutes * 60)
        with self._lock:
            active = {}
            for key, session in self._sessions.items():
                last_ts = session.get("last_event")
                if last_ts:
                    if isinstance(last_ts, datetime):
                        last_epoch = last_ts.timestamp()
                    else:
                        last_epoch = last_ts
                    if last_epoch > cutoff:
                        active[key] = session
            return active

    def cleanup_stale_sessions(self, hours: int = 24) -> int:
        """Remove sessions inactive for more than N hours."""
        cutoff = time.time() - (hours * 3600)
        removed = 0
        with self._lock:
            stale_keys = []
            for key, session in self._sessions.items():
                last_ts = session.get("last_event")
                if last_ts:
                    if isinstance(last_ts, datetime):
                        last_epoch = last_ts.timestamp()
                    else:
                        last_epoch = last_ts
                    if last_epoch < cutoff:
                        stale_keys.append(key)
            for key in stale_keys:
                del self._sessions[key]
                removed += 1
        return removed

    def reset(self) -> None:
        """Reset all session activity data."""
        with self._lock:
            self._sessions = {}


# Global instances
_global_metrics_collector: Optional[EventMetricsCollector] = None
_global_audit_logger: Optional[EventAuditLogger] = None
_global_session_tracker: Optional[SessionActivityTracker] = None


def get_event_metrics_collector() -> EventMetricsCollector:
    """Get the global metrics collector."""
    global _global_metrics_collector
    if _global_metrics_collector is None:
        _global_metrics_collector = EventMetricsCollector()
        _global_metrics_collector.subscribe()
    return _global_metrics_collector


def get_event_audit_logger() -> EventAuditLogger:
    """Get the global audit logger."""
    global _global_audit_logger
    if _global_audit_logger is None:
        _global_audit_logger = EventAuditLogger()
        _global_audit_logger.subscribe()
    return _global_audit_logger


def get_session_activity_tracker() -> SessionActivityTracker:
    """Get the global session tracker."""
    global _global_session_tracker
    if _global_session_tracker is None:
        _global_session_tracker = SessionActivityTracker()
        _global_session_tracker.subscribe()
    return _global_session_tracker


def initialize_event_consumers() -> None:
    """Initialize all event consumers."""
    get_event_metrics_collector()
    get_event_audit_logger()
    get_session_activity_tracker()
    logger.info("Event consumers initialized")


def shutdown_event_consumers() -> None:
    """Shut down all event consumers."""
    global _global_metrics_collector, _global_audit_logger, _global_session_tracker
    if _global_metrics_collector:
        _global_metrics_collector.unsubscribe()
    if _global_audit_logger:
        _global_audit_logger.unsubscribe()
    if _global_session_tracker:
        _global_session_tracker.unsubscribe()
    logger.info("Event consumers shut down")


__all__ = [
    "EventConsumer",
    "EventMetricsCollector",
    "EventAuditLogger",
    "SessionActivityTracker",
    "get_event_metrics_collector",
    "get_event_audit_logger",
    "get_session_activity_tracker",
    "initialize_event_consumers",
    "shutdown_event_consumers",
]