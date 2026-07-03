"""Experience mining best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def read_text_snippet_safe(path: Path, *, limit: int = 500) -> str | None:
    def _run() -> str:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]

    result = safe_best_effort(
        _run,
        label="experience_mining.read_snippet",
        default=None,
    )
    return str(result) if result is not None else None


def collect_recent_edit_paths_safe(
    workspace: Path,
    *,
    cutoff: float,
    max_items: int = 30,
) -> list[Path]:
    def _run() -> list[Path]:
        out: list[Path] = []
        for fp in workspace.rglob("*"):
            if not fp.is_file():
                continue
            rel = fp.relative_to(workspace)
            if any(p.startswith(".") for p in rel.parts):
                continue
            if fp.suffix.lower() not in {".py", ".md", ".yaml", ".yml", ".toml", ".json"}:
                continue
            try:
                if fp.stat().st_mtime >= cutoff:
                    out.append(fp)
            except OSError:
                continue
            if len(out) >= max_items:
                break
        return out

    result = safe_best_effort(
        _run,
        label="experience_mining.recent_edits",
        default=[],
    )
    return result if isinstance(result, list) else []


def run_mining_source_safe(
    fn: Callable[[], list[Any]],
    *,
    label: str,
) -> tuple[list[Any], str | None]:
    def _run() -> list[Any]:
        return fn()

    result = safe_best_effort(_run, label=f"experience_mining.{label}", default=None)
    if isinstance(result, list):
        return result, None
    return [], f"{label}: skipped"
