"""Per-session AgentLoop lifecycle registry for Gateway handlers."""

from __future__ import annotations

import logging
import time
import threading
from collections.abc import Callable, Iterable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

_evict_notify_hook: Callable[[str], None] | None = None


def set_evict_notify_hook(hook: Callable[[str], None] | None) -> None:
    global _evict_notify_hook
    _evict_notify_hook = hook


class _TrackedSessionDict(dict[str, Any]):
    def __init__(self, registry: "GatewaySessionRegistry", initial: dict[str, Any] | None = None) -> None:
        self._registry = registry
        super().__init__()
        if initial:
            self.update(initial)

    def __setitem__(self, key: str, value: Any) -> None:
        normalized = str(key or "default")
        with self._registry._lock:
            super().__setitem__(normalized, value)
            self._registry._last_active_at[normalized] = self._registry._now()

    def update(  # type: ignore[override]
        self,
        other: Mapping[str, Any] | Iterable[tuple[str, Any]] = (),
        /,
        **kwargs: Any,
    ) -> None:
        items = dict(other, **kwargs)
        for key, value in items.items():
            self[key] = value


class GatewaySessionRegistry:
    """Track Gateway AgentLoop instances, health, and lifecycle finalization."""

    def __init__(
        self,
        loop_factory: Callable[[str], Any],
        *,
        finalize: Callable[[Any], Any] | None = None,
        on_session_removed: Callable[[str], None] | None = None,
        max_sessions: int = 128,
        idle_ttl_seconds: float = 3600,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._loop_factory = loop_factory
        self._finalize = finalize
        self._on_session_removed = on_session_removed
        self.max_sessions = max(1, int(max_sessions or 1))
        self.idle_ttl_seconds = max(0.0, float(idle_ttl_seconds or 0))
        self._now = now or time.monotonic
        self._lock = threading.RLock()
        self.sessions: dict[str, Any] = _TrackedSessionDict(self)
        self.health_by_session: dict[str, dict[str, Any]] = {}
        self._last_active_at: dict[str, float] = {}
        self._session_locks: dict[str, threading.RLock] = {}
        self._active_sessions: set[str] = set()
        self._pending_session_entries = 0
        self._resetting_all = False
        self._reset_condition = threading.Condition(self._lock)

    def get_or_create(self, session_key: str) -> Any:
        key = str(session_key or "default")
        with self._lock:
            self._wait_for_reset_all_locked(key)
            if key not in self.sessions:
                self.sessions[key] = self._loop_factory(key)
            self.touch(key)
            loop = self.sessions[key]
            self.enforce_lru()
        self._publish_session_gauges()
        return loop

    def session_lock(self, session_key: str) -> threading.RLock:
        key = str(session_key or "default")
        with self._lock:
            self._wait_for_reset_all_locked()
            lock = self._session_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._session_locks[key] = lock
            return lock

    def enter_session(self, session_key: str) -> threading.RLock:
        """Enter a session turn and mark it active before work begins."""
        key = str(session_key or "default")
        while True:
            with self._lock:
                self._wait_for_reset_all_locked()
                lock = self._session_locks.get(key)
                if lock is None:
                    lock = threading.RLock()
                    self._session_locks[key] = lock
                self._pending_session_entries += 1
            lock.acquire()
            with self._lock:
                self._pending_session_entries -= 1
                self._reset_condition.notify_all()
                if not self._resetting_all:
                    self._active_sessions.add(key)
                    return lock
            lock.release()

    def exit_session(self, session_key: str, lock: threading.RLock) -> None:
        key = str(session_key or "default")
        try:
            with self._lock:
                self._active_sessions.discard(key)
                self._reset_condition.notify_all()
        finally:
            lock.release()

    def mark_active(self, session_key: str) -> None:
        with self._lock:
            self._wait_for_reset_all_locked()
            self._active_sessions.add(str(session_key or "default"))
        self._publish_session_gauges()

    def mark_inactive(self, session_key: str) -> None:
        with self._lock:
            self._active_sessions.discard(str(session_key or "default"))
            self._reset_condition.notify_all()
        self._publish_session_gauges()

    def _publish_session_gauges(self) -> None:
        from butler.gateway.session_registry_ops import publish_session_gauges_safe

        with self._lock:
            publish_session_gauges_safe(
                session_count=len(self.sessions),
                active_turns=len(self._active_sessions),
            )

    def is_session_active(self, session_key: str) -> bool:
        """True while a gateway turn holds the session lock (AgentLoop running)."""
        key = str(session_key or "default")
        with self._lock:
            return key in self._active_sessions

    def touch(self, session_key: str) -> None:
        with self._lock:
            self._last_active_at[str(session_key or "default")] = self._now()

    def last_active_at(self, session_key: str) -> float:
        with self._lock:
            return self._last_active_at.get(str(session_key or "default"), 0.0)

    def set_health(self, session_key: str, health: dict[str, Any]) -> None:
        with self._lock:
            self.health_by_session[str(session_key or "default")] = dict(health)

    def get_health(self, session_key: str) -> dict[str, Any]:
        with self._lock:
            return dict(self.health_by_session.get(str(session_key or "default"), {}))

    def reset_sessions_for_chat(self, *, platform: str, chat_id: str) -> list[str]:
        """Drop all cached loops for ``platform:chat_id:*`` (e.g. after /切换 project)."""
        plat = str(platform or "unknown").strip() or "unknown"
        cid = str(chat_id or "default").strip() or "default"
        prefix = f"{plat}:{cid}:"
        with self._lock:
            keys = [k for k in list(self.sessions.keys()) if k.startswith(prefix)]
        cleared: list[str] = []
        for key in keys:
            self.reset(key)
            cleared.append(key)
        if cleared:
            logger.info(
                "Reset %d gateway session(s) for chat %s after project switch",
                len(cleared),
                prefix,
            )
        return cleared

    def reset(self, session_key: str, *, skip_finalize: bool = False) -> None:
        key = str(session_key or "default")
        with self.session_lock(key):
            with self._lock:
                loop = self.sessions.pop(key, None)
                self.health_by_session.pop(key, None)
                self._last_active_at.pop(key, None)
                self._active_sessions.discard(key)
                self._session_locks.pop(key, None)
        self._notify_session_removed(key)
        if not skip_finalize:
            self._finalize_loop(loop)

    def reset_all(self, *, wait_timeout: float = 120.0) -> None:
        finalized: set[int] = set()
        with self._lock:
            self._wait_for_reset_all_locked()
            self._resetting_all = True
        deadline = self._now() + max(1.0, float(wait_timeout))
        try:
            with self._lock:
                while (self._active_sessions or self._pending_session_entries) and self._now() < deadline:
                    self._reset_condition.wait(timeout=1.0)
                if self._active_sessions or self._pending_session_entries:
                    logger.error(
                        "reset_all timed out after %.0fs (active=%s pending=%d); forcing clear",
                        wait_timeout,
                        sorted(self._active_sessions),
                        self._pending_session_entries,
                    )
                    self._active_sessions.clear()
                    self._pending_session_entries = 0
                items = list(self.sessions.items())
                self.sessions.clear()
                self.health_by_session.clear()
                self._last_active_at.clear()
                self._active_sessions.clear()
                self._session_locks.clear()
        finally:
            with self._lock:
                self._resetting_all = False
                self._reset_condition.notify_all()
        for key, _loop in items:
            self._notify_session_removed(key)
        for _key, loop in items:
            if id(loop) in finalized:
                continue
            finalized.add(id(loop))
            self._finalize_loop(loop)

    def evict_idle(self) -> list[str]:
        with self._lock:
            if self.idle_ttl_seconds <= 0 or self._resetting_all:
                return []
            cutoff = self._now() - self.idle_ttl_seconds
            expired = [
                key for key in self.sessions
                if key not in self._active_sessions
                and self._last_active_at.get(key, 0.0) < cutoff
            ]
        evicted: list[str] = []
        for key in expired:
            if self._reset_if_still_idle(key, cutoff):
                evicted.append(key)
        if evicted and _evict_notify_hook is not None:
            from butler.gateway.session_registry_ops import run_evict_notify_hook_safe

            for key in evicted:
                run_evict_notify_hook_safe(_evict_notify_hook, key)
        return evicted

    def enforce_lru(self) -> list[str]:
        loops_to_finalize: list[Any] = []
        with self._lock:
            if self._resetting_all:
                return []
            evicted: list[str] = []
            while len(self.sessions) > self.max_sessions:
                candidates = [key for key in self.sessions if key not in self._active_sessions]
                if not candidates:
                    break
                oldest = min(candidates, key=lambda key: self._last_active_at.get(key, 0.0))
                evicted.append(oldest)
                loop = self.sessions.pop(oldest, None)
                self.health_by_session.pop(oldest, None)
                self._last_active_at.pop(oldest, None)
                self._session_locks.pop(oldest, None)
                self._notify_session_removed(oldest)
                loops_to_finalize.append(loop)
        for loop in loops_to_finalize:
            self._finalize_loop(loop)
        return evicted

    def _finalize_loop(self, loop: Any) -> None:
        if loop is None or self._finalize is None:
            return
        self._finalize(loop)

    def _wait_for_reset_all_locked(self, session_key: str | None = None) -> None:
        while self._resetting_all and (
            session_key is None or session_key not in self._active_sessions
        ):
            self._reset_condition.wait()

    def _reset_if_still_idle(self, session_key: str, cutoff: float) -> bool:
        key = str(session_key or "default")
        loop = None
        with self.session_lock(key):
            with self._lock:
                if (
                    self._resetting_all
                    or key in self._active_sessions
                    or self._last_active_at.get(key, 0.0) >= cutoff
                ):
                    return False
                loop = self.sessions.pop(key, None)
                self.health_by_session.pop(key, None)
                self._last_active_at.pop(key, None)
                self._session_locks.pop(key, None)
        if loop is not None:
            self._notify_session_removed(key)
        self._finalize_loop(loop)
        return loop is not None

    def _notify_session_removed(self, session_key: str) -> None:
        from butler.gateway.session_registry_ops import notify_session_removed_safe

        notify_session_removed_safe(self._on_session_removed, session_key)
