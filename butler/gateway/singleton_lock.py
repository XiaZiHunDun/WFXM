"""Ensure at most one Butler gateway process polls WeChat per machine."""

from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_LOCK_FD: int | None = None


def _lock_path() -> Path:
    data_home = os.getenv("BUTLER_DATA_HOME", "").strip()
    base = Path(data_home).expanduser() if data_home else Path.home() / ".butler"
    base.mkdir(parents=True, exist_ok=True)
    return base / "gateway.singleton.lock"


def acquire_gateway_singleton_lock() -> None:
    """Take an exclusive flock; exit the process if another gateway holds it."""
    global _LOCK_FD
    if _LOCK_FD is not None:
        return
    import fcntl

    path = _lock_path()
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        msg = (
            "Another Butler gateway is already running (singleton lock held). "
            "Run: bash scripts/butler-gateway-ops.sh restart"
        )
        logger.error(msg)
        raise SystemExit(2)
    _LOCK_FD = fd
    os.write(fd, f"{os.getpid()}\n".encode())
    atexit.register(release_gateway_singleton_lock)


def release_gateway_singleton_lock() -> None:
    global _LOCK_FD
    if _LOCK_FD is None:
        return
    import fcntl

    try:
        fcntl.flock(_LOCK_FD, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(_LOCK_FD)
    except OSError:
        pass
    _LOCK_FD = None


__all__ = ["acquire_gateway_singleton_lock", "release_gateway_singleton_lock"]
