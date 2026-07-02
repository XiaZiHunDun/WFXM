"""Delegate job report finalization and post-run hooks (P2-F)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def attach_delegate_diff_summary(report: Any, job: Any) -> None:
    """Collect git diff --stat after delegate finishes and append to report summary."""
    if not report or not hasattr(report, "summary"):
        return

    def _run() -> None:
        from butler.tools.git_tools import _run_git, git_read_enabled

        if not git_read_enabled():
            return

        workspace = None
        try:
            from butler.project.manager import ProjectManager

            pm = ProjectManager()
            proj = pm.active_project
            if proj and hasattr(proj, "workspace"):
                workspace = str(proj.workspace)
        except ImportError:
            return
        if not workspace:
            return

        diff = _run_git(["diff", "--stat", "--cached"], workdir=workspace)
        if diff.get("exit_code") != 0:
            diff = _run_git(["diff", "--stat"], workdir=workspace)
        if diff.get("exit_code") != 0:
            return

        stat_output = (diff.get("stdout") or "").strip()
        if not stat_output:
            return

        diff_lines = stat_output.split("\n")
        if len(diff_lines) > 15:
            diff_lines = diff_lines[:14] + [f"... 还有 {len(diff_lines) - 14} 个文件"]

        diff_section = "\n\n📊 变更摘要:\n" + "\n".join(f"  {line}" for line in diff_lines)
        current = report.summary or ""
        if len(current) + len(diff_section) < 4000:
            report.summary = current + diff_section

    safe_best_effort(_run, label="delegate_job.diff_summary", default=None)


def record_delegate_turn_done(
    job: Any,
    *,
    success: bool,
    result: Any,
) -> None:
    if not job.child_session_key:
        return

    def _run() -> None:
        from butler.core.session_transcript import record_generic_event

        record_generic_event(
            job.child_session_key,
            "delegate_turn_done",
            {
                "task_id": job.task_id,
                "success": success,
                "background": True,
                "iterations": getattr(result, "iterations", 0) if result else 0,
            },
        )

    safe_best_effort(_run, label="delegate_job.turn_done_event", default=None)


def record_delegate_observability(
    job: Any,
    *,
    success: bool,
    issues: list[Any],
    dev_engine: dict[str, Any] | None,
) -> None:
    def _run() -> None:
        from butler.ops.delegate_failure_capture import maybe_capture_from_delegate_result
        from butler.ops.langfuse_tracer import finish_delegate_trace
        from butler.tools.delegate_phases import peek_dev_engine_summary

        engine = dev_engine
        if engine is None:
            engine = peek_dev_engine_summary(
                job.child_session_key or job.session_key,
                job.role,
            )
        finish_delegate_trace(
            job.child_session_key or job.session_key,
            success=success,
            metadata={
                "task_id": job.task_id,
                "role": job.role,
                "background": True,
                "dev_engine": engine or {},
            },
        )
        maybe_capture_from_delegate_result(
            role=job.role,
            task=job.task,
            success=success,
            issues=issues,
            parent_session_key=job.session_key,
            child_session_key=job.child_session_key or job.session_key,
            task_id=job.task_id,
            dev_engine=engine,
        )

    safe_best_effort(_run, label="delegate_job.observability", default=None)


def handle_background_delegate_failure(job: Any, exc: BaseException) -> None:
    import logging

    log = logging.getLogger(__name__)
    log.exception("Background delegate failed task_id=%s: %s", job.task_id, exc)
    from butler.tools.registry import _finalize_delegate_failure

    _finalize_delegate_failure(
        role=job.role,
        task=job.task,
        exc=exc,
        task_id=job.task_id,
        session_key=job.session_key,
    )


__all__ = [
    "attach_delegate_diff_summary",
    "handle_background_delegate_failure",
    "record_delegate_observability",
    "record_delegate_turn_done",
]
