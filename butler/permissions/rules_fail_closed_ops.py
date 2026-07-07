"""Fail-closed permission guards and diagnostics buffer (P0-A / R2-11)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.permissions.rules_context import is_session_tool_result_readable

logger = logging.getLogger(__name__)

_MAX_PERMISSION_FAILURE_ENTRIES = 50
_MAX_PERMISSION_FAILURE_ERROR_LEN = 200
_permission_failures: list[dict[str, Any]] = []


def recent_permission_failures() -> list[dict[str, Any]]:
    """Read the module-level permission-failure diagnostics buffer."""
    return list(_permission_failures)


def reset_permission_failures() -> None:
    """Clear the permission-failure diagnostics buffer (test helper)."""
    _permission_failures.clear()


def record_permission_failure(check: str, exc: BaseException) -> None:
    """Append a permission-check failure to the diagnostics buffer (FIFO bounded)."""
    logger.error(
        "Permission check %s failed (fail-closed); %s",
        check,
        exc,
        exc_info=exc,
    )
    _permission_failures.append({
        "check": check,
        "error": str(exc)[:_MAX_PERMISSION_FAILURE_ERROR_LEN],
        "type": type(exc).__name__,
    })
    if len(_permission_failures) > _MAX_PERMISSION_FAILURE_ENTRIES:
        del _permission_failures[
            : len(_permission_failures) - _MAX_PERMISSION_FAILURE_ENTRIES
        ]


def path_outside_workspace(path_str: str, workspace: Path) -> bool:
    if not path_str:
        return False
    if is_session_tool_result_readable(path_str):
        return False
    try:
        root = workspace.expanduser().resolve()
        target = Path(path_str).expanduser()
        if not target.is_absolute():
            target = (root / target).resolve()
        else:
            target = target.resolve()
        return not target.is_relative_to(root)
    except Exception as exc:
        logger.warning("path_outside_workspace check failed (fail-closed): %s", exc)
        return True


def experiment_block_or_fail_closed(
    tool_name: str,
    args: dict[str, Any],
    workspace: Path,
) -> str | None:
    try:
        from butler.experiments.mode import check_experiment_mode_block
    except Exception as exc:
        record_permission_failure("experiment_mode_block_import", exc)
        return "experiment mode 守护不可用 (import 失败); 拒绝该调用"
    try:
        block = check_experiment_mode_block(tool_name, args, workspace=workspace)
        if block:
            return str(block)
        return None
    except Exception as exc:
        record_permission_failure("experiment_mode_block", exc)
        return "experiment mode 守护异常 (fail-closed); 拒绝该调用"


def workflow_step_block_or_fail_closed(
    tool_name: str,
    workspace: Path,
) -> str | None:
    try:
        from butler.execution_context import get_current_workflow_step
    except Exception as exc:
        record_permission_failure("workflow_step_resolve_import", exc)
        return "workflow step 解析器不可用 (import 失败); 拒绝该调用"
    try:
        step_id = get_current_workflow_step()
    except Exception as exc:
        record_permission_failure("workflow_step_resolve", exc)
        return "workflow step 解析器异常 (fail-closed); 拒绝该调用"
    if not step_id:
        return None
    try:
        from butler.permissions.rules import evaluate_workflow_step_permission

        step_decision = evaluate_workflow_step_permission(
            tool_name,
            step_id,
            workspace=workspace,
        )
    except Exception as exc:
        record_permission_failure("workflow_step_decision", exc)
        return "workflow step 决策异常 (fail-closed); 拒绝该调用"
    if step_decision is not None and not step_decision.allowed:
        return str(step_decision.reason)
    return None


__all__ = [
    "experiment_block_or_fail_closed",
    "path_outside_workspace",
    "recent_permission_failures",
    "record_permission_failure",
    "reset_permission_failures",
    "workflow_step_block_or_fail_closed",
]
