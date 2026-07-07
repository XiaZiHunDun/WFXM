"""Workflow validation parse best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_workflow_yaml_safe(path: Path) -> tuple[Any | None, str | None]:
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data, None
    except Exception as exc:
        return None, f"parse error: {exc}"
