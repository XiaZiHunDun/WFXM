"""Execpolicy load best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def append_home_execpolicy_path_safe(paths: list[Path]) -> None:
    def _run() -> Path | None:
        from butler.config import get_butler_home

        home = get_butler_home() / "execpolicy.yaml"
        return home if home.is_file() else None

    result = safe_best_effort(
        _run,
        label="execpolicy.home_path",
        default=None,
    )
    if isinstance(result, Path):
        paths.append(result)


def load_execpolicy_yaml_safe(path: Path) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}

    result = safe_best_effort(
        _run,
        label=f"execpolicy.load.{path.name}",
        default=None,
    )
    if result is None:
        logger.warning("execpolicy %s unreadable", path)
        return None
    return result if isinstance(result, dict) else {}
