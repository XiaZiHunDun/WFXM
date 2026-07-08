"""Best-effort and fail-closed helpers for delegate_task (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def apply_delegate_success_gates(
    *,
    base: bool,
    issues: list[str],
    category: str,
    category_meta: dict[str, Any] | None,
    project: Any,
    role: str,
    dev_engine: dict[str, Any] | None,
    task: str,
    task_preview: str,
    changes: list[Any],
    messages: list[Any] | None = None,
    summary: str = "",
) -> tuple[bool, list[str]]:
    def _run() -> tuple[bool, list[str]]:
        from butler.dev_engine.b9_delegate_gate import (
            apply_b9_pytest_success_gate,
            apply_coding_strict_pilot_gate,
            apply_dev_auto_verify_success_gate,
            apply_dev_review_strict_gate,
        )
        from butler.tools.delegate_delete_gate import apply_delegate_delete_verify_gate

        out_issues = list(issues or [])
        ok, out_issues = apply_b9_pytest_success_gate(
            category=category,
            category_meta=category_meta,
            project=project,
            base_success=base,
            issues=out_issues,
        )
        ok, out_issues = apply_dev_auto_verify_success_gate(
            role=role,
            base_success=ok,
            issues=out_issues,
            dev_engine=dev_engine,
            task=task,
            task_preview=task_preview or (task or "")[:200],
            changes=changes,
            category_meta=category_meta,
        )
        ok, out_issues = apply_coding_strict_pilot_gate(
            category=category,
            category_meta=category_meta,
            role=role,
            base_success=ok,
            issues=out_issues,
            dev_engine=dev_engine,
        )
        ok, out_issues = apply_delegate_delete_verify_gate(
            base_success=ok,
            issues=out_issues,
            task=task,
            task_preview=task_preview or (task or "")[:200],
            changes=changes,
            project=project,
            messages=messages,
            summary=summary,
        )
        final = apply_dev_review_strict_gate(
            category=category,
            category_meta=category_meta,
            role=role,
            base_success=ok,
            issues=out_issues,
            dev_engine=dev_engine,
        )
        if isinstance(final, tuple) and len(final) == 2:
            f_ok, f_issues = final
            return bool(f_ok), list(f_issues) if isinstance(f_issues, list) else out_issues
        return ok, out_issues

    result = safe_best_effort(
        _run,
        label="delegate_impl.success_gates",
        default=(base, list(issues or [])),
    )
    if isinstance(result, tuple) and len(result) == 2:
        ok, out = result
        return bool(ok), list(out) if isinstance(out, list) else list(issues or [])
    return base, list(issues or [])


def inject_corrective_recall_safe(name: str, args: dict[str, Any], result: str) -> str:
    def _run() -> str:
        from butler.memory.corrective_recall import (
            build_corrective_recall_block,
            should_trigger_corrective,
        )

        if not should_trigger_corrective(name, result):
            return result
        task_hint = str(args.get("task") or args.get("query") or args.get("path") or "")
        block = build_corrective_recall_block(
            task=task_hint,
            tool_name=name,
            error_excerpt=result[:400],
        )
        if block:
            return f"{result}\n\n{block}"
        return result

    out = safe_best_effort(
        _run,
        label="delegate_impl.corrective_recall",
        default=result,
    )
    return out if isinstance(out, str) else result


def run_subagent_stop_hooks_safe(
    *,
    role: str,
    agent_id: str,
    success: bool,
    task_id: str = "",
    session_key: str = "",
    summary_preview: str = "",
) -> None:
    def _run() -> None:
        from butler.hooks.runner import run_subagent_stop_hooks

        run_subagent_stop_hooks(
            agent_type=role,
            agent_id=agent_id,
            success=success,
            task_id=task_id,
            session_key=session_key,
            summary_preview=summary_preview,
        )

    safe_best_effort(_run, label="delegate_impl.subagent_stop_hooks", default=None)


def capture_delegate_failure_safe(
    *,
    role: str,
    task: str,
    summary: str,
    session_key: str,
    task_id: str,
    project: str,
) -> None:
    def _run() -> None:
        from butler.ops.delegate_failure_capture import maybe_capture_from_delegate_result

        maybe_capture_from_delegate_result(
            role=role,
            task=task,
            success=False,
            issues=[summary[:500]],
            parent_session_key=session_key,
            child_session_key=session_key,
            task_id=task_id,
            project=project,
            dev_engine=None,
        )

    safe_best_effort(_run, label="delegate_impl.failure_capture", default=None)


def notify_delegate_finished_safe(bridge: Any, report: Any) -> None:
    def _run() -> None:
        if bridge is not None:
            bridge.notify_delegate_finished(report)

    safe_best_effort(_run, label="delegate_impl.finished_notify", default=None)


def run_delegate_task_loud(
    *,
    role: str,
    task: str,
    context: str,
    category: str,
    depth: int,
    finalize_failure: Any,
) -> str:
    """Run delegate phases; single fail-closed boundary for tool entry."""
    from butler.execution_context import get_current_turn_bridge
    from butler.tools.delegate_phases import (
        DelegateRunState,
        _build_user_message,
        _format_delegate_result,
        _prepare_delegate_task,
        _record_delegate_state,
        _resolve_subagent,
        _run_subagent_loop,
    )

    state = DelegateRunState(
        role=role,
        task=task,
        context=context,
        category=category,
        depth=depth,
        original_context=context,
        bridge=get_current_turn_bridge(),
    )
    try:
        _prepare_delegate_task(state)
        if state.early_return:
            return str(state.early_return)
        _resolve_subagent(state)
        _build_user_message(state)
        _record_delegate_state(state)
        if state.early_return:
            return str(state.early_return)
        async_payload = _run_subagent_loop(state)
        if async_payload is not None:
            return str(async_payload)
        return str(_format_delegate_result(state, state.sync_result))
    except Exception as exc:
        logger.error("Delegation to %s failed: %s", role, exc)
        project_name = ""
        if state.project is not None:
            project_name = str(getattr(state.project, "name", "") or "")
        return str(
            finalize_failure(
                role=state.role,
                task=state.task,
                exc=exc,
                task_id=state.task_id,
                session_key=state.session_key,
                project=project_name,
            )
        )
