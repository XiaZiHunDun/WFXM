"""Secrets file load best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def load_secrets_yaml_safe(path: Path) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("secrets yaml root must be a mapping")
        return data

    result = safe_best_effort(
        _run,
        label="config_secrets.load_yaml",
        default={},
    )
    return result if isinstance(result, dict) else {}
