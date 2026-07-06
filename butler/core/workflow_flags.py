"""Workflow feature flags (external-agent-reports PR-X1)."""

from __future__ import annotations

from butler.env_parse import env_truthy


def workflow_rescue_enabled() -> bool:
    return bool(env_truthy("BUTLER_WORKFLOW_RESCUE", default=True))
def workflow_optional_enabled() -> bool:
    return bool(env_truthy("BUTLER_WORKFLOW_OPTIONAL", default=True))
def workflow_clear_child_enabled() -> bool:
    return bool(env_truthy("BUTLER_WORKFLOW_CLEAR_CHILD", default=False))
__all__ = [
    "workflow_clear_child_enabled",
    "workflow_optional_enabled",
    "workflow_rescue_enabled",
]
