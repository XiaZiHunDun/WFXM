"""Hook loader best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_butler_global_hooks_safe(
    load_file: Callable[[Path], list[Any]],
) -> list[Any]:
    try:
        from butler.config import get_butler_settings

        settings = get_butler_settings()
        rules: list[Any] = []
        cfg_path = settings.config_yaml_path
        if cfg_path.is_file():
            rules.extend(load_file(cfg_path))
        rules.extend(load_file(settings.butler_home / ".butler" / "hooks.yaml"))
        return rules
    except Exception as exc:
        logger.debug("Global hooks load skipped: %s", exc)
        return []


def parse_hooks_yaml_dict_safe(path: Path) -> dict[str, Any] | None:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("PyYAML not installed; skipping %s", path)
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load hooks %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None
