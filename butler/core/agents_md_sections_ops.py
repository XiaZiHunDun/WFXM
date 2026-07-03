"""AGENTS.md workspace resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.design_md_sections_ops import resolve_active_project_workspace_safe


def resolve_agents_md_workspace_safe() -> Path | None:
    return resolve_active_project_workspace_safe()
