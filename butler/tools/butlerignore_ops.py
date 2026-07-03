"""Butlerignore best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def current_workspace_root_safe() -> Path | None:
    def _run() -> Path:
        from butler.tools.path_safety import current_workspace_root

        root = current_workspace_root()
        if root is None:
            raise ValueError("workspace root unavailable")
        return Path(root)

    result = safe_best_effort(
        _run,
        label="butlerignore.workspace_root",
        default=None,
    )
    return result if isinstance(result, Path) else None
