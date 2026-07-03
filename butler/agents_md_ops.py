"""Agent markdown frontmatter best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def parse_yaml_frontmatter_safe(raw: str) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        import yaml

        loaded = yaml.safe_load(raw)
        if not isinstance(loaded, dict):
            raise ValueError("frontmatter is not a mapping")
        return loaded

    result = safe_best_effort(_run, label="agents_md.frontmatter_yaml", default=None)
    return result if isinstance(result, dict) else None
