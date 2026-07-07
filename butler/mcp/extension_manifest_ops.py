"""Extension manifest YAML load best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from butler.core.best_effort import safe_best_effort


def load_yaml_mapping_safe(path: Path) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("yaml root must be a mapping")
        return data

    result = safe_best_effort(
        _run,
        label="extension_manifest.load_yaml",
        default=None,
    )
    return dict(result) if isinstance(result, dict) else None
