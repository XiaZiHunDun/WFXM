"""Single-flight reply admission per session (OpenClaw reply-turn-admission subset)."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass

from butler.env_parse import env_truthy


@dataclass(frozen=True)
class AdmissionToken:
    session_key: str
    token_id: str
    admitted_at: float


_LOCK = threading.RLock()
_ACTIVE: dict[str, AdmissionToken] = {}


def reply_admission_enabled() -> bool:
    return env_truthy("BUTLER_REPLY_ADMISSION", default=True)


def try_admit(session_key: str) -> AdmissionToken | None:
    """Claim session for one inbound reply turn; None if already active."""
    if not reply_admission_enabled():
        return AdmissionToken(
            session_key=str(session_key or "default"),
            token_id="disabled",
            admitted_at=time.monotonic(),
        )
    key = str(session_key or "default").strip() or "default"
    with _LOCK:
        if key in _ACTIVE:
            return None
        token = AdmissionToken(
            session_key=key,
            token_id=uuid.uuid4().hex[:12],
            admitted_at=time.monotonic(),
        )
        _ACTIVE[key] = token
        return token


def release(token: AdmissionToken | None) -> None:
    if token is None or token.token_id == "disabled":
        return
    key = token.session_key
    with _LOCK:
        current = _ACTIVE.get(key)
        if current is not None and current.token_id == token.token_id:
            _ACTIVE.pop(key, None)


def is_admitted(session_key: str) -> bool:
    key = str(session_key or "default").strip() or "default"
    with _LOCK:
        return key in _ACTIVE


def clear_session(session_key: str) -> None:
    key = str(session_key or "default").strip() or "default"
    with _LOCK:
        _ACTIVE.pop(key, None)
