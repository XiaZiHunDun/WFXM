"""Workflow run snapshot checkpoint best-effort helpers (P0-A)."""

from __future__ import annotations


def workflow_checkpoint_enabled_safe() -> bool | None:
    try:
        from butler.core.meta_flags import workflow_checkpoint_enabled

        return bool(workflow_checkpoint_enabled())
    except Exception:
        return None
