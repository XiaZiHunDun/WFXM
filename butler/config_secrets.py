"""Provider API keys outside config.yaml (Dify credential-at-rest subset, stdlib-first)."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def secrets_file_enabled() -> bool:
    raw = os.getenv("BUTLER_SECRETS_FILE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def secrets_path(home: Path | None = None) -> Path:
    from butler.config import get_butler_home

    base = home or get_butler_home()
    override = os.getenv("BUTLER_SECRETS_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return base / "secrets.yaml"


def _ensure_private_mode(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            mode = path.stat().st_mode & 0o777
            if mode & 0o077:
                path.chmod(0o600)
        else:
            path.touch(mode=0o600)
            path.chmod(0o600)
    except OSError as exc:
        logger.warning("secrets chmod failed (file may be world-readable): %s", exc)


def load_secrets_dict(home: Path | None = None, *, decrypt: bool = False) -> dict[str, Any]:
    if not secrets_file_enabled():
        return {}
    path = secrets_path(home)
    if not path.is_file():
        return {}
    from butler.config_secrets_ops import load_secrets_yaml_safe

    data = load_secrets_yaml_safe(path)
    if not data:
        return {}
    if decrypt:
        return _decrypt_secrets_dict(data)
    return data


def _decrypt_secrets_dict(data: dict[str, Any]) -> dict[str, Any]:
    from butler.config_secrets_crypto import decrypt_secret_value

    out = dict(data)
    providers = out.get("providers")
    if isinstance(providers, dict):
        decrypted_providers: dict[str, Any] = {}
        for name, entry in providers.items():
            if isinstance(entry, str):
                decrypted_providers[str(name)] = decrypt_secret_value(entry)
            elif isinstance(entry, dict):
                row = dict(entry)
                for field in ("api_key", "key", "token", "secret"):
                    if field in row:
                        row[field] = decrypt_secret_value(str(row.get(field) or ""))
                decrypted_providers[str(name)] = row
            else:
                decrypted_providers[str(name)] = entry
        out["providers"] = decrypted_providers
    for key, val in list(out.items()):
        if key == "providers" or not isinstance(val, str):
            continue
        out[key] = decrypt_secret_value(val)
    return out


def provider_secrets(home: Path | None = None) -> dict[str, str]:
    """Map provider name -> api_key from secrets file."""
    data = load_secrets_dict(home, decrypt=True)
    providers = data.get("providers")
    if not isinstance(providers, dict):
        return {}
    out: dict[str, str] = {}
    for name, entry in providers.items():
        if isinstance(entry, str) and entry.strip():
            out[str(name).strip()] = entry.strip()
            continue
        if isinstance(entry, dict):
            key = str(entry.get("api_key") or entry.get("key") or "").strip()
            if key:
                out[str(name).strip()] = key
    return out


def merge_secrets_into_settings(settings: Any) -> None:
    """Fill missing provider api_key from secrets.yaml (env still wins)."""
    secrets = provider_secrets(settings.butler_home)
    if not secrets:
        return
    for name, key in secrets.items():
        if not key:
            continue
        pc = settings.providers.get(name)
        if pc is None:
            from butler.config import ProviderConfig

            settings.providers[name] = ProviderConfig(name=name, api_key=key)
        elif not (pc.api_key or "").strip():
            pc.api_key = key


def write_provider_secret(
    provider: str,
    api_key: str,
    *,
    home: Path | None = None,
) -> Path:
    from butler.config_secrets_crypto import encrypt_secret_value

    path = secrets_path(home)
    _ensure_private_mode(path)
    data = load_secrets_dict(home)
    providers = data.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        data["providers"] = providers
    stored_key = encrypt_secret_value(str(api_key).strip())
    providers[str(provider).strip()] = {"api_key": stored_key}
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _ensure_private_mode(path)
    return path


def encrypt_secrets_file(*, home: Path | None = None, dry_run: bool = True) -> dict[str, Any]:
    """Encrypt plaintext entries in secrets.yaml (requires BUTLER_SECRETS_ENCRYPT=1)."""
    from butler.config_secrets_crypto import (
        count_encrypted_entries,
        encrypt_secrets_dict,
        secrets_encrypt_enabled,
    )

    path = secrets_path(home)
    if not secrets_file_enabled():
        return {"ok": False, "error": "BUTLER_SECRETS_FILE=0"}
    if not secrets_encrypt_enabled():
        return {"ok": False, "error": "BUTLER_SECRETS_ENCRYPT 未开"}
    if not path.is_file():
        return {"ok": False, "error": f"no secrets file: {path}"}
    data = load_secrets_dict(home)
    before_enc, before_total = count_encrypted_entries(data)
    changed = encrypt_secrets_dict(data)
    after_enc, after_total = count_encrypted_entries(data)
    result = {
        "ok": True,
        "path": str(path),
        "dry_run": dry_run,
        "changed": changed,
        "encrypted_before": before_enc,
        "encrypted_after": after_enc,
        "total_secrets": after_total or before_total,
    }
    if dry_run or changed <= 0:
        return result
    _ensure_private_mode(path)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _ensure_private_mode(path)
    return result


def secrets_status_line(home: Path | None = None) -> str:
    from butler.config_secrets_crypto import count_encrypted_entries, secrets_encrypt_enabled

    path = secrets_path(home)
    if not secrets_file_enabled():
        return "凭证文件: 关 (BUTLER_SECRETS_FILE=0)"
    if not path.is_file():
        return f"凭证文件: 无 ({path})"
    try:
        mode = stat.filemode(path.stat().st_mode)
    except OSError:
        mode = "?"
    n = len(provider_secrets(home))
    enc_flag = "开" if secrets_encrypt_enabled() else "关"
    raw = load_secrets_dict(home)
    enc_n, total_n = count_encrypted_entries(raw)
    enc_note = f" · 加密={enc_flag}"
    if total_n:
        enc_note += f" ({enc_n}/{total_n} 条目已加密)"
    return f"凭证文件: {path.name} mode={mode} providers={n}{enc_note}"
