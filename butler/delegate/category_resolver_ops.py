"""Delegate category YAML load best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def load_delegate_categories_from_path_safe(path: Path) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("delegate categories yaml root must be a mapping")
        cats = data.get("categories")
        if not isinstance(cats, dict):
            return {}
        return dict(cats)

    result = safe_best_effort(
        _run,
        label="category_resolver.load_yaml",
        default={},
    )
    return dict(result) if isinstance(result, dict) else {}
