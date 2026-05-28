"""Optional per-project git worktree root (OpenCode project worktree subset)."""

from __future__ import annotations

import logging
from pathlib import Path

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def project_worktree_enabled() -> bool:
    return env_truthy("BUTLER_PROJECT_WORKTREE", default=False)


def read_worktree_spec(workspace: Path) -> str:
    """Return raw worktree path from project.yaml (may be relative)."""
    cfg = workspace / "project.yaml"
    if not cfg.is_file():
        return ""
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    raw = data.get("worktree")
    return str(raw or "").strip()


def effective_workspace(workspace: Path) -> Path:
    """
    Resolve tool/git cwd when ``worktree`` is set and BUTLER_PROJECT_WORKTREE=1.
    Falls back to project workspace when path missing.
    """
    base = workspace.expanduser().resolve()
    if not project_worktree_enabled():
        return base
    spec = read_worktree_spec(base)
    if not spec:
        return base
    target = Path(spec).expanduser()
    if not target.is_absolute():
        target = (base / target).resolve()
    else:
        target = target.resolve()
    if target.is_dir():
        return target
    logger.warning("Project worktree path not found: %s (using workspace)", target)
    return base
