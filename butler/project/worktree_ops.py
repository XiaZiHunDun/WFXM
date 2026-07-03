"""Project worktree spec read best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

import yaml

from butler.core.best_effort import safe_best_effort


def read_project_yaml_worktree_safe(workspace: Path) -> str:
    cfg = workspace / "project.yaml"
    if not cfg.is_file():
        return ""

    def _run() -> str:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("project.yaml is not a mapping")
        return str(data.get("worktree") or "").strip()

    result = safe_best_effort(
        _run,
        label="worktree.read_spec",
        default="",
    )
    return str(result or "").strip()
