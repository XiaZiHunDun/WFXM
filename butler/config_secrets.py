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


def load_secrets_dict(home: Path | None = None) -> dict[str, Any]:
    if not secrets_file_enabled():
        return {}
    path = secrets_path(home)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("secrets.yaml read failed: %s", exc)
        return {}


def provider_secrets(home: Path | None = None) -> dict[str, str]:
    """Map provider name -> api_key from secrets file."""
    data = load_secrets_dict(home)
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
    path = secrets_path(home)
    _ensure_private_mode(path)
    data = load_secrets_dict(home)
    providers = data.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        data["providers"] = providers
    providers[str(provider).strip()] = {"api_key": str(api_key).strip()}
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _ensure_private_mode(path)
    return path


def secrets_status_line(home: Path | None = None) -> str:
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
    return f"凭证文件: {path.name} mode={mode} providers={n}"
