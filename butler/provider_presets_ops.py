"""Provider preset file load helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def load_presets_yaml_safe(path: Path) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("presets yaml root must be a mapping")
        return data

    result = safe_best_effort(
        _run,
        label="provider_presets.load_yaml",
        default=None,
    )
    return result if isinstance(result, dict) else None
