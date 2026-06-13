"""Background and foreground delegate execution."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DelegatePushTarget:
    adapter: Any
    chat_id: str
    loop: Any


@dataclass
class DelegateJob:
    agent: Any
    orch: Any
    user_msg: str
    raw_user_msg: str
    role: str
    task: str
    session_key: str
    child_session_key: str
    task_id: str
    category_meta: dict[str, Any] = field(default_factory=dict)
    bridge: Any | None = None
    push_target: DelegatePushTarget | None = None
    use_async_push: bool = False


def build_async_delegate_tool_result(
    *,
    task_id: str,
    child_session_key: str,
    role: str,
    task_preview: str,
    category: str = "",
) -> str:
    role_label = _delegate_role_label(role)
    payload: dict[str, Any] = {
        "success": True,
        "background": True,
        "async": True,
        "task_id": task_id,
        "child_session_key": child_session_key,
        "headline": f"{role_label}已在后台执行",
        "summary": (
            "委派任务已提交后台；完成后将单独微信通知。"
            "可用 /任务 查看状态，/详细 查看最近报告。"
        ),
        "message": (
            f"已后台委派 {role_label}（task_id={task_id}）。"
            "父会话可继续其它工作。"
        ),
    }
    if category:
        payload["category"] = category
    if task_preview:
        payload["task_preview"] = task_preview[:200]
    return json.dumps(payload, ensure_ascii=False)


def push_delegate_completion(
    report: Any,
    *,
    bridge: Any | None = None,
    push_target: DelegatePushTarget | None = None,
    use_async_push: bool = False,
) -> bool:
    """WeChat notify when a delegate finishes (sync or background)."""
    from butler.gateway.completion_notify import (
        build_report_push_text,
        delegate_completion_enabled,
        deliver_completion_push,
    )

    if not delegate_completion_enabled():
        return False

    prefix = "📋 委派已完成（后台）" if use_async_push else "📋 委派阶段完成"
    text = build_report_push_text(report, prefix=prefix)

    if push_target is not None and push_target.loop is not None:
        import asyncio

        async def _send() -> None:
            await deliver_completion_push(
                push_target.adapter,
                push_target.chat_id,
                text,
                kind="delegate",
            )

        try:
            asyncio.run_coroutine_threadsafe(_send(), push_target.loop)
            return True
        except Exception as exc:
            logger.warning("Async delegate push schedule failed: %s", exc)

    if bridge is not None and not use_async_push:
        try:
            bridge.notify_delegate_finished(report)
            return True
        except Exception as exc:
            logger.warning("Bridge delegate notify failed: %s", exc)

    try:
        from butler.runtime.notify import push_runtime_message

        return push_runtime_message("[Butler] 委派完成", text)
    except Exception as exc:
        logger.warning("Runtime delegate push failed: %s", exc)
        return False


def run_delegate_job(job: DelegateJob) -> None:
    """Execute delegate agent loop (intended for background thread)."""
    result = None
    success = False
    try:
        if job.bridge is not None:
            try:
                from butler.gateway.outbound_bridge import set_current_bridge

                set_current_bridge(job.bridge)
            except Exception as exc:
                logger.debug("run delegate job skipped: %s", exc)
        from butler.execution_context import use_execution_context

        with use_execution_context(job.orch, session_key=job.child_session_key or job.session_key):
            from butler.runtime.delegate_registry import (
                register_delegate_loop,
                unregister_delegate_loop,
            )

            register_delegate_loop(job.session_key, job.agent)
            run_cbs = None
            try:
                from butler.ops.langfuse_tracer import delegate_run_callbacks

                run_cbs = delegate_run_callbacks(
                    parent_session_key=job.session_key,
                    child_session_key=job.child_session_key or job.session_key,
                    role=job.role,
                    task=job.task,
                    task_id=job.task_id,
                )
            except Exception as exc:
                logger.debug("background delegate LangFuse callbacks skipped: %s", exc)
            try:
                if run_cbs is not None:
                    result = job.agent.run(job.user_msg, run_callbacks=run_cbs)
                else:
                    result = job.agent.run(job.user_msg)
            finally:
                unregister_delegate_loop(job.session_key, job.agent)

        from butler.session.lifecycle import sync_turn_memory

        sync_turn_memory(
            job.orch,
            job.raw_user_msg,
            (result.final_response or "") if result else "",
            interrupted=result.status.value == "interrupted" if result else False,
            status=result.status if result else None,
            session_id=job.session_key,
        )

        from butler.tools.delegate_impl import finalize_delegate_success
        from butler.tools.registry import (
            _extract_changes_from_messages,
            _extract_issues_from_messages,
            _run_subagent_stop_hooks,
        )

        changes = _extract_changes_from_messages(result.messages) if result else []
        issues = _extract_issues_from_messages(result.messages) if result else []
        project = None
        try:
            project = job.orch.project_manager.get_current() if job.orch else None
        except Exception:
            project = None
        if result:
            from butler.tools.delegate_phases import peek_dev_engine_summary

            dev_engine = peek_dev_engine_summary(
                job.child_session_key or job.session_key or "_default",
                job.role,
            )
            success, issues = finalize_delegate_success(
                result,
                changes,
                issues,
                category=str(job.category_meta.get("category") or ""),
                category_meta=job.category_meta,
                project=project,
                role=job.role,
                dev_engine=dev_engine,
            )
        else:
            success = False
            dev_engine = None
        role_label = _delegate_role_label(job.role)
        if success:
            headline = f"{role_label}已完成任务"
        elif any("DEV_VERIFY_GATE" in str(i) for i in issues):
            headline = f"{role_label}已完成编辑但未通过验证"
        else:
            headline = f"{role_label}未能完成任务"
        summary_text = (result.final_response or "").strip() if result else ""
        if not summary_text:
            summary_text = (
                "DELEGATE_EMPTY_RESPONSE: 子代理未返回有效摘要。"
                "请缩小任务范围或换 category/role 后重试。"
            )
            success = False
            headline = f"{role_label}返回空结果"

        if job.child_session_key:
            try:
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
            except Exception as exc:
                logger.debug("run delegate job skipped: %s", exc)
        from butler.report import AgentReport, cache_report
        from butler.runtime.task_store import complete_task

        task_preview = (job.task or "").strip()[:200]
        report = AgentReport(
            headline=headline,
            summary=summary_text or "(无输出)",
            changes=changes,
            issues=issues,
            success=success,
            task_preview=task_preview,
            task_id=job.task_id,
            child_session_key=job.child_session_key,
            iterations=getattr(result, "iterations", 0) if result else 0,
            tool_calls=getattr(result, "tool_calls_made", 0) if result else 0,
            tokens_used=getattr(result, "total_tokens", 0) if result else 0,
            elapsed_seconds=getattr(result, "elapsed_seconds", 0.0) if result else 0.0,
        )
        cache_report(report, session_key=job.session_key)
        complete_task(
            job.task_id,
            success=success,
            report_headline=report.headline,
            summary=report.summary,
        )
        _run_subagent_stop_hooks(
            role=job.role,
            agent_id=job.task_id or f"delegate-{job.role}",
            success=success,
            task_id=job.task_id,
            session_key=job.session_key,
            summary_preview=report.summary,
        )
        _try_attach_diff_summary(report, job)
        push_delegate_completion(
            report,
            bridge=job.bridge,
            push_target=job.push_target,
            use_async_push=job.use_async_push,
        )
        try:
            from butler.tools.delegate_phases import peek_dev_engine_summary

            dev_engine = peek_dev_engine_summary(
                job.child_session_key or job.session_key,
                job.role,
            )
            from butler.ops.langfuse_tracer import finish_delegate_trace
            from butler.ops.delegate_failure_capture import maybe_capture_from_delegate_result

            finish_delegate_trace(
                job.child_session_key or job.session_key,
                success=success,
                metadata={
                    "task_id": job.task_id,
                    "role": job.role,
                    "background": True,
                    "dev_engine": dev_engine or {},
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
                dev_engine=dev_engine,
            )
        except Exception as obs_exc:
            logger.debug("background delegate observability skipped: %s", obs_exc)
        logger.info(
            "Background delegate finished task_id=%s success=%s",
            job.task_id,
            success,
        )
    except Exception as exc:
        logger.exception("Background delegate failed task_id=%s: %s", job.task_id, exc)
        from butler.tools.registry import _finalize_delegate_failure

        _finalize_delegate_failure(
            role=job.role,
            task=job.task,
            exc=exc,
            task_id=job.task_id,
            session_key=job.session_key,
        )
    finally:
        try:
            from butler.core.delegate_semaphore import release_delegate_slot

            release_delegate_slot(job.session_key)
        except Exception as exc:
            logger.debug("run delegate job skipped: %s", exc)
def _try_attach_diff_summary(report: Any, job: DelegateJob) -> None:
    """Collect git diff --stat after delegate finishes and append to report summary."""
    if not report or not hasattr(report, "summary"):
        return
    try:
        from butler.tools.git_tools import git_read_enabled, _run_git

        if not git_read_enabled():
            return

        workspace = None
        proj = None
        try:
            from butler.project.manager import ProjectManager
            pm = ProjectManager()
            proj = pm.active_project
            if proj and hasattr(proj, "workspace"):
                workspace = str(proj.workspace)
        except Exception as exc:
            logger.debug("try attach diff summary skipped: %s", exc)
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
    except Exception as exc:
        logger.debug("Diff summary collection skipped: %s", exc)


def _delegate_role_label(role: str) -> str:
    from butler.tools.builtin_impl import _delegate_role_label as _canonical
    return _canonical(role)
