"""Track in-flight delegate AgentLoops for parent-session interrupt propagation."""

from __future__ import annotations

import logging
import threading
import weakref
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_BY_PARENT: dict[str, list[weakref.ReferenceType[Any]]] = {}


def _parent_key(session_key: str) -> str:
    raw = str(session_key or "").strip()
    if "::delegate::" in raw:
        return raw.split("::delegate::", 1)[0].strip() or raw
    return raw


def register_delegate_loop(parent_session_key: str, loop: Any) -> None:
    """Register a nested AgentLoop running under ``parent_session_key``."""
    parent = _parent_key(parent_session_key)
    if not parent:
        return
    ref = weakref.ref(loop)
    with _LOCK:
        rows = _BY_PARENT.setdefault(parent, [])
        rows[:] = [r for r in rows if r() is not None]
        rows.append(ref)


def unregister_delegate_loop(parent_session_key: str, loop: Any) -> None:
    parent = _parent_key(parent_session_key)
    if not parent:
        return
    with _LOCK:
        rows = _BY_PARENT.get(parent, [])
        if not rows:
            return
        kept = [r for r in rows if r() is not None and r() is not loop]
        if kept:
            _BY_PARENT[parent] = kept
        else:
            _BY_PARENT.pop(parent, None)


def interrupt_delegates_for_session(session_key: str) -> int:
    """Interrupt all active delegate loops for this parent session. Returns count."""
    parent = _parent_key(session_key)
    if not parent:
        return 0
    interrupted = 0
    with _LOCK:
        rows = list(_BY_PARENT.get(parent, []))
    for ref in rows:
        loop = ref()
        if loop is None:
            continue
        try:
            if hasattr(loop, "interrupt"):
                loop.interrupt()
                interrupted += 1
        except Exception as exc:
            logger.debug("Delegate interrupt failed: %s", exc)
    if interrupted:
        logger.info("Interrupted %d delegate loop(s) for session=%s", interrupted, parent)
    return interrupted
