"""Thread-safe singleton primitives for Butler.

Provides two building blocks:

* ``lazy_singleton`` — decorator that wraps a zero-argument factory into a
  thread-safe, lazily-initialised singleton using double-checked locking.

* ``SingletonSlot`` — manual per-key singleton slot for accessors that need
  to build different instances depending on a config / key argument.

Both utilities rely **only** on the standard-library ``threading`` module,
making them safe to import anywhere in the project.
"""

from __future__ import annotations

import threading
from typing import Callable, Generic, TypeVar

T = TypeVar("T")
K = TypeVar("K")

__all__ = ["lazy_singleton", "SingletonSlot"]


class lazy_singleton(Generic[T]):
    """Thread-safe lazy singleton decorator using double-checked locking.

    Wraps a zero-argument *factory* so that the first call invokes the
    factory and every subsequent call returns the same cached instance.
    Concurrent first calls are serialised so the factory runs **exactly
    once**.

    A ``.reset()`` method is attached to the wrapped callable for tests
    and teardown scenarios.

    Usage::

        @lazy_singleton
        def get_db() -> Database:
            return Database.connect("postgres://localhost")

        db = get_db()   # factory called once
        db2 = get_db()  # same instance
        assert db is db2

        get_db.reset()  # clear cache (useful in tests)

    Thread-safety is guaranteed through double-checked locking: the
    fast-path (already initialised) is lock-free, while the initialisation
    path takes a lock only when necessary.
    """

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._lock = threading.Lock()
        self._instance: T | None = None
        self.__name__ = factory.__name__
        self.__qualname__ = factory.__qualname__
        self.__doc__ = factory.__doc__

    def __call__(self) -> T:
        if self._instance is not None:
            return self._instance
        with self._lock:
            if self._instance is None:
                self._instance = self._factory()
        return self._instance

    def reset(self) -> None:
        """Discard the cached instance so the next call re-runs the factory."""
        with self._lock:
            self._instance = None


class SingletonSlot(Generic[K, T]):
    """Thread-safe per-key singleton slot.

    Unlike :class:`lazy_singleton`, which caches a single global instance,
    ``SingletonSlot`` maintains an independent singleton **per key**. This
    is useful when you have an accessor that constructs different objects
    depending on a configuration / identifier argument (e.g. a tenant ID,
    model name, or connection string).

    Each key has its own lock, so concurrent access to *different* keys
    does not contend.

    Usage::

        slot = SingletonSlot()

        def factory(tenant_id: str) -> Client:
            return Client(tenant_id)

        c1 = slot.get("tenant-a", lambda: factory("tenant-a"))
        c2 = slot.get("tenant-a", lambda: factory("tenant-a"))
        c3 = slot.get("tenant-b", lambda: factory("tenant-b"))

        assert c1 is c2
        assert c1 is not c3
        assert "tenant-a" in slot
        slot.reset("tenant-a")   # clear only tenant-a
        slot.reset()             # clear everything

    Type-var notes
    -------------
    * ``K`` — the key type (e.g. ``str``, ``int``, ``Enum``).
    * ``T`` — the cached instance type.
    """

    def __init__(self) -> None:
        self._instances: dict[K, T] = {}
        self._locks: dict[K, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def get(self, key: K, factory: Callable[[], T]) -> T:
        """Return the singleton instance for *key*, creating it via
        *factory* if it does not yet exist.

        Thread-safety is guaranteed: concurrent calls with the same *key*
        will result in exactly one invocation of *factory*.
        """
        existing = self._instances.get(key)
        if existing is not None:
            return existing

        with self._global_lock:
            key_lock = self._locks.get(key)
            if key_lock is None:
                key_lock = threading.Lock()
                self._locks[key] = key_lock

        with key_lock:
            existing = self._instances.get(key)
            if existing is not None:
                return existing
            instance = factory()
            self._instances[key] = instance
            return instance

    def reset(self, key: K | None = None) -> None:
        """Clear the cached instance for *key*, or all keys if *key* is
        ``None``.
        """
        with self._global_lock:
            if key is None:
                self._instances.clear()
                self._locks.clear()
            else:
                self._instances.pop(key, None)
                self._locks.pop(key, None)

    def __contains__(self, key: K) -> bool:
        """Return ``True`` if *key* currently has a cached instance."""
        return key in self._instances
