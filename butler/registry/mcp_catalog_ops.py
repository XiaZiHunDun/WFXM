"""MCP catalog best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def ensure_catalog_integrity_safe() -> None:
    def _run() -> None:
        from butler.registry.catalog_integrity import ensure_catalog_integrity

        ensure_catalog_integrity()

    safe_best_effort(_run, label="mcp_catalog.integrity", default=None)


def load_yaml_dict_safe(path: Path) -> dict[str, Any] | None:
    def _run() -> dict[str, Any] | None:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None

    result = safe_best_effort(_run, label="mcp_catalog.load_yaml", default=None)
    return result if isinstance(result, dict) else None


def merge_remote_catalog_entries_safe(
    out: list[Any],
    seen: set[str],
) -> None:
    def _run() -> None:
        from butler.registry.mcp_catalog_remote import load_remote_catalog_entries

        for entry in load_remote_catalog_entries():
            if entry.id.lower() in seen:
                continue
            seen.add(entry.id.lower())
            out.append(entry)

    safe_best_effort(_run, label="mcp_catalog.remote_merge", default=None)


def load_json_file_safe(path: Path) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    result = safe_best_effort(_run, label="mcp_catalog.load_json", default={})
    return result if isinstance(result, dict) else {}
