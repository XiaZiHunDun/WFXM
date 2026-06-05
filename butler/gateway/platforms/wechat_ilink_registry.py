"""R1-12 — thread-safe, GC-friendly registry for live WeChat adapters.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-12

The original ``butler/gateway/platforms/wechat_ilink.py`` carried a
module-level ``_LIVE_ADAPTERS: Dict[str, Any] = {}`` with no lock.
The long-poll loop in ``_poll_loop`` registered adapters via
``_LIVE_ADAPTERS[self._token] = self`` while the one-shot
``send_wechat_direct`` path looked them up via
``_LIVE_ADAPTERS.get(resolved_token)`` and ``disconnect()`` removed
them with ``_LIVE_ADAPTERS.pop(self._token, None)``. Under multi-
account / reconnect-storm pressure, these three callers could race
on the same dict across coroutine and thread boundaries.

This module replaces that bare ``dict`` with a small
:class:`AdapterRegistry` that pairs:

* :class:`weakref.WeakValueDictionary` — a strong reference held by
  the registry is *not* enough to keep an adapter alive. When the
  rest of the program drops its last strong reference (e.g. the
  caller of ``send_wechat_direct`` goes out of scope), the entry
  is reclaimed automatically and we don't accumulate zombie
  adapters across reconnect cycles.
* :class:`threading.RLock` — concurrent register / unregister /
  get from the poll loop and the send path are serialised. Reads
  also take the lock to keep the snapshot consistent with any
  concurrent unregister, at the cost of a tiny bit of contention.

The module exposes a single :data:`_ADAPTER_REGISTRY` singleton so
the three call sites in ``wechat_ilink.py`` (disconnect, line 491
and send_wechat_direct, line 1257) and ``wechat_ilink_phases.py``
(``_start_poll_and_register``, line 277) can all share state
without re-instantiating the registry.
"""

from __future__ import annotations

import threading
import weakref
from typing import Any, Optional


class AdapterRegistry:
    """Thread-safe, GC-friendly registry of live WeChat adapters.

    Replaces the module-level ``_LIVE_ADAPTERS: Dict`` from audit R1-12.
    Backed by :class:`weakref.WeakValueDictionary` so dropped adapters
    are reclaimed automatically; :class:`threading.RLock` serialises
    mutations so concurrent register / unregister from the poll loop
    and the send path cannot corrupt the dict.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._adapters: "weakref.WeakValueDictionary[str, Any]" = (
            weakref.WeakValueDictionary()
        )

    def register(self, token: str, adapter: Any) -> None:
        """Insert or overwrite the adapter for ``token``.

        Equivalent to ``self._adapters[token] = adapter`` under the
        lock; last writer wins when multiple threads race on the
        same token.
        """
        with self._lock:
            self._adapters[token] = adapter

    def unregister(self, token: str) -> bool:
        """Remove the adapter for ``token`` if present.

        Returns ``True`` if an entry was removed, ``False`` if the
        token was not registered. Safe to call on a missing token
        (mirrors the old ``_LIVE_ADAPTERS.pop(self._token, None)``
        contract — disconnect is idempotent).
        """
        with self._lock:
            return self._adapters.pop(token, None) is not None

    def get(self, token: str) -> Optional[Any]:
        """Return the adapter for ``token`` or ``None`` if missing.

        Read-only ``WeakValueDictionary`` access is technically safe
        without the lock, but taking the lock keeps the snapshot
        consistent with any concurrent unregister.
        """
        with self._lock:
            return self._adapters.get(token)

    def __contains__(self, token: object) -> bool:
        with self._lock:
            return token in self._adapters

    def __len__(self) -> int:
        with self._lock:
            return len(self._adapters)

    def live_count(self) -> int:
        """Lock-safe count, intended for diagnostics and tests.

        Wraps ``len`` in the lock so it cannot race a concurrent
        register / unregister and raise
        ``RuntimeError: dictionary changed size during iteration``.
        """
        with self._lock:
            return len(self._adapters)


# Module-level singleton (preserves the import-and-use shape of the
# old ``_LIVE_ADAPTERS`` dict while routing every access through the
# registry's lock + weakref semantics). All three call sites in
# ``wechat_ilink.py`` (disconnect + send_wechat_direct) and
# ``wechat_ilink_phases.py`` (``_start_poll_and_register``) import
# this name.
_ADAPTER_REGISTRY = AdapterRegistry()
