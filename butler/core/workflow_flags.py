"""Workflow orchestration feature flags."""

from __future__ import annotations

from butler.env_parse import env_truthy


def workflow_clear_child_enabled() -> bool:
    return env_truthy("BUTLER_WORKFLOW_CLEAR_CHILD", default=False)


__all__ = ["workflow_clear_child_enabled"]
