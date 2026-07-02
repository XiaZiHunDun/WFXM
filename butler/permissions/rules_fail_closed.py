"""Fail-closed permission guards (re-export shim)."""

from butler.permissions.rules_fail_closed_ops import (
    experiment_block_or_fail_closed,
    path_outside_workspace,
    recent_permission_failures,
    record_permission_failure,
    reset_permission_failures,
    workflow_step_block_or_fail_closed,
)

__all__ = [
    "experiment_block_or_fail_closed",
    "path_outside_workspace",
    "recent_permission_failures",
    "record_permission_failure",
    "reset_permission_failures",
    "workflow_step_block_or_fail_closed",
]
