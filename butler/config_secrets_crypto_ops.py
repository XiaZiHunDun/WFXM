"""Secrets crypto best-effort helpers (P0-A)."""

from __future__ import annotations

import base64
import logging
from typing import Any

logger = logging.getLogger(__name__)

_FERNET_PREFIX = "FERNET:"


def init_fernet_safe(key: str) -> Any | None:
    try:
        from cryptography.fernet import Fernet

        return Fernet(key.encode("utf-8"))
    except ImportError:
        logger.warning("cryptography not installed; secrets encryption disabled")
        return None
    except Exception as exc:
        logger.warning("secrets Fernet init failed: %s", exc)
        return None


def decrypt_fernet_value_safe(fernet: Any, encrypted_text: str) -> str:
    try:
        encrypted = base64.urlsafe_b64decode(encrypted_text)
        return fernet.decrypt(encrypted).decode("utf-8")
    except Exception as exc:
        logger.warning("secrets Fernet decrypt failed: %s", exc)
        return ""
