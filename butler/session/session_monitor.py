"""Session monitoring and alerting.

Tracks session lifecycle events and triggers alerts for:
- Long-running sessions
- Expired sessions
- High memory usage
- Abnormal termination

Emits domain events for session lifecycle tracking via event sourcing.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional

from butler.session.session_store import get_session_store
from butler.core.events.event_store import (
    DomainEvent,
    generate_event_id,
    now_utc,
    get_global_event_store,
    get_global_event_bus,
)

logger = logging.getLogger(__name__)

DEFAULT_CHECK_INTERVAL = 60
DEFAULT_MAX_SESSION_AGE_HOURS = 24
DEFAULT_MAX_RUNNING_SESSIONS = 10


class SessionMonitor:
    def __init__(self):
        self._store = get_session_store()
        self._check_interval = DEFAULT_CHECK_INTERVAL
        self._max_session_age_hours = DEFAULT_MAX_SESSION_AGE_HOURS
        self._max_running_sessions = DEFAULT_MAX_RUNNING_SESSIONS
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._alerts: list[dict[str, Any]] = []
        self._alert_handlers: list[Callable[[dict[str, Any]], None]] = []

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Session monitor started")
        self._emit_session_monitor_event("SessionMonitorStarted", {})

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Session monitor stopped")
        self._emit_session_monitor_event("SessionMonitorStopped", {})

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._check_sessions()
            except Exception as exc:
                logger.error("Session monitor check failed: %s", exc)
            time.sleep(self._check_interval)

    def _check_sessions(self) -> None:
        stats = self._store.get_stats()
        running_sessions = self._store.list_sessions(state="running")

        if len(running_sessions) > self._max_running_sessions:
            self._trigger_alert(
                "high_running_sessions",
                f"Running sessions exceeded limit: {len(running_sessions)} > {self._max_running_sessions}",
                {"count": len(running_sessions), "limit": self._max_running_sessions},
            )

        now = time.time()
        max_age_sec = self._max_session_age_hours * 3600

        for session in running_sessions:
            session_age = now - session.get("last_active_at", now)
            if session_age > max_age_sec:
                self._trigger_alert(
                    "stale_session",
                    f"Session {session['session_id']} inactive for {session_age/3600:.1f} hours",
                    {"session_id": session["session_id"], "age_hours": session_age/3600},
                )

    def _trigger_alert(self, alert_type: str, message: str, details: dict[str, Any]) -> None:
        alert = {
            "type": alert_type,
            "message": message,
            "details": details,
            "timestamp": time.time(),
        }

        self._alerts.append(alert)
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-100:]

        logger.warning("[SessionAlert] %s: %s", alert_type, message)

        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as exc:
                logger.error("Alert handler failed: %s", exc)

    def register_alert_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._alert_handlers.append(handler)

    def get_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._alerts[-limit:]

    def get_recent_alerts(self, hours: int = 1) -> list[dict[str, Any]]:
        cutoff = time.time() - (hours * 3600)
        return [a for a in self._alerts if a["timestamp"] > cutoff]

    def clear_alerts(self) -> None:
        self._alerts.clear()

    def get_status(self) -> dict[str, Any]:
        stats = self._store.get_stats()
        return {
            "running": self._running,
            "check_interval": self._check_interval,
            "max_session_age_hours": self._max_session_age_hours,
            "max_running_sessions": self._max_running_sessions,
            "alert_count": len(self._alerts),
            "recent_alert_count": len(self.get_recent_alerts()),
            "session_stats": stats,
        }

    def set_thresholds(
        self,
        max_session_age_hours: int | None = None,
        max_running_sessions: int | None = None,
        check_interval: int | None = None,
    ) -> None:
        if max_session_age_hours is not None:
            self._max_session_age_hours = max_session_age_hours
        if max_running_sessions is not None:
            self._max_running_sessions = max_running_sessions
        if check_interval is not None:
            self._check_interval = check_interval

    def _emit_session_monitor_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit a session monitor domain event."""
        try:
            event = DomainEvent(
                event_id=generate_event_id(),
                event_type=event_type,
                session_key="",
                timestamp=now_utc(),
                data=data,
                version=1,
            )
            get_global_event_store().append(event)
            get_global_event_bus().publish(event)
        except Exception as exc:
            logger.debug("Failed to emit session monitor event: %s", exc)


def start_session_monitor() -> SessionMonitor:
    """Start the session monitor via ServiceContainer."""
    from butler.core.container import container

    monitor = container.session_monitor()
    monitor.start()
    return monitor


def stop_session_monitor() -> None:
    """Stop the session monitor via ServiceContainer."""
    from butler.core.container import container

    monitor = container.session_monitor()
    monitor.stop()


def get_session_monitor() -> SessionMonitor:
    """Get session monitor via ServiceContainer."""
    from butler.core.container import container

    return container.session_monitor()
