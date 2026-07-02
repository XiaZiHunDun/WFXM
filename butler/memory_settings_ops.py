"""Best-effort helpers for memory settings (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from butler.core.best_effort import safe_best_effort


def load_yaml_memory_section_safe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}

    def _run() -> dict[str, Any]:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        mem = data.get("memory")
        return mem if isinstance(mem, dict) else {}

    result = safe_best_effort(_run, label="memory_settings.yaml_load", default={})
    return result if isinstance(result, dict) else {}
