"""Optional Fernet at-rest encryption for ``secrets.yaml`` provider keys."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_FERNET_PREFIX = "FERNET:"


def secrets_encrypt_enabled() -> bool:
    return env_truthy("BUTLER_SECRETS_ENCRYPT", default=False)


def _get_fernet():
    if not secrets_encrypt_enabled():
        return None
    key = os.getenv("BUTLER_SECRETS_ENCRYPT_KEY", "").strip()
    if not key:
        logger.warning(
            "BUTLER_SECRETS_ENCRYPT=1 but BUTLER_SECRETS_ENCRYPT_KEY is empty; "
            "encryption disabled"
        )
        return None
    try:
        from cryptography.fernet import Fernet

        return Fernet(key.encode("utf-8"))
    except ImportError:
        logger.warning("cryptography not installed; secrets encryption disabled")
        return None
    except Exception as exc:
        logger.warning("secrets Fernet init failed: %s", exc)
        return None


def is_encrypted_value(value: str) -> bool:
    return str(value or "").startswith(_FERNET_PREFIX)


def decrypt_secret_value(value: str) -> str:
    text = str(value or "")
    if not text.startswith(_FERNET_PREFIX):
        return text
    f = _get_fernet()
    if f is None:
        logger.warning("encrypted secret present but Fernet unavailable")
        return ""
    try:
        encrypted = base64.urlsafe_b64decode(text[len(_FERNET_PREFIX) :])
        return f.decrypt(encrypted).decode("utf-8")
    except Exception as exc:
        logger.warning("secrets Fernet decrypt failed: %s", exc)
        return ""


def encrypt_secret_value(value: str) -> str:
    plain = str(value or "")
    if not plain or is_encrypted_value(plain):
        return plain
    f = _get_fernet()
    if f is None:
        return plain
    encrypted = f.encrypt(plain.encode("utf-8"))
    return _FERNET_PREFIX + base64.urlsafe_b64encode(encrypted).decode("ascii")


def _encrypt_mapping_values(raw: dict[str, Any]) -> int:
    changed = 0
    for key, entry in list(raw.items()):
        if isinstance(entry, str) and entry.strip():
            enc = encrypt_secret_value(entry.strip())
            if enc != entry:
                raw[key] = enc
                changed += 1
            continue
        if not isinstance(entry, dict):
            continue
        for field in ("api_key", "key", "token", "secret"):
            val = str(entry.get(field) or "").strip()
            if not val:
                continue
            enc = encrypt_secret_value(val)
            if enc != val:
                entry[field] = enc
                changed += 1
    return changed


def encrypt_secrets_dict(data: dict[str, Any]) -> int:
    """Encrypt provider keys in-place; returns number of values encrypted."""
    if not isinstance(data, dict):
        return 0
    changed = 0
    providers = data.get("providers")
    if isinstance(providers, dict):
        changed += _encrypt_mapping_values(providers)
    for key, val in list(data.items()):
        if key == "providers":
            continue
        if isinstance(val, str) and val.strip():
            enc = encrypt_secret_value(val.strip())
            if enc != val:
                data[key] = enc
                changed += 1
    return changed


def count_encrypted_entries(data: dict[str, Any]) -> tuple[int, int]:
    """Return (encrypted_count, total_secret_values)."""
    encrypted = 0
    total = 0

    def _walk_value(val: str) -> None:
        nonlocal encrypted, total
        text = str(val or "").strip()
        if not text:
            return
        total += 1
        if is_encrypted_value(text):
            encrypted += 1

    if not isinstance(data, dict):
        return 0, 0
    providers = data.get("providers")
    if isinstance(providers, dict):
        for entry in providers.values():
            if isinstance(entry, str):
                _walk_value(entry)
            elif isinstance(entry, dict):
                for field in ("api_key", "key", "token", "secret"):
                    _walk_value(str(entry.get(field) or ""))
    for key, val in data.items():
        if key == "providers" or not isinstance(val, str):
            continue
        _walk_value(val)
    return encrypted, total


__all__ = [
    "count_encrypted_entries",
    "decrypt_secret_value",
    "encrypt_secret_value",
    "encrypt_secrets_dict",
    "is_encrypted_value",
    "secrets_encrypt_enabled",
]
