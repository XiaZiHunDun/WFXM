"""Tenant store encryption best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def build_fernet_safe(key: str) -> Any | None:
    def _run() -> Any:
        from cryptography.fernet import Fernet

        return Fernet(key.encode("utf-8"))

    result = safe_best_effort(
        _run,
        label="tenant_store.fernet_init",
        default=None,
    )
    if result is None:
        logger.warning("Fernet init failed or cryptography unavailable")
    return result


def decrypt_fernet_payload_safe(fernet: Any, payload_b64: bytes) -> str | None:
    def _run() -> str:
        return str(fernet.decrypt(payload_b64).decode("utf-8"))

    result = safe_best_effort(
        _run,
        label="tenant_store.fernet_decrypt",
        default=None,
    )
    if result is None:
        logger.warning("Fernet decryption failed")
    return result if isinstance(result, str) else None
