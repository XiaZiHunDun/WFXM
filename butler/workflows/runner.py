"""Execute project workflows through :class:`~butler.task_orchestrator.TaskOrchestrator`."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from butler.report import AgentReport, cache_report
from butler.task_orchestrator import AgentSpawnConfig, TaskNode, TaskGraphResult, TaskOrchestrator
from butler.workflows.schema import WorkflowDef

logger = logging.getLogger(__name__)

_QA_LOOP_NAMES = frozenset({"dev-qa-loop", "ui-dev-qa-loop"})


async def _maybe_replan_dev_qa_loop(
    workflow: WorkflowDef,
    nodes: list[TaskNode],
    graph: TaskGraphResult,
    *,
    orchestrator: TaskOrchestrator,
    var_pool: Any,
    on_progress: Any = None,
) -> TaskGraphResult:
    """On QA FAIL, re-run implement once (MetaGPT PlanSnapshot / 主线 N P1 subset)."""
    if workflow.name not in _QA_LOOP_NAMES:
        return graph
    qa = graph.nodes.get("qa")
    impl_node = next((n for n in nodes if n.id == "implement"), None)
    qa_node = next((n for n in nodes if n.id == "qa"), None)
    if qa is None or impl_node is None or qa_node is None:
        return graph
    from butler.core.plan_snapshot import (
        build_plan_snapshot,
        qa_response_is_fail,
        replan_implement_task,
        update_step_outcome,
    )
    from butler.env_parse import env_truthy

    if qa.success or not qa_response_is_fail(qa.response or ""):
        return graph
    try:
        from butler.env_parse import int_env

        max_replan = int_env("BUTLER_WORKFLOW_QA_REPLAN_MAX", 1, min=0)
    except ValueError:
        max_replan = 1
    if max_replan <= 0 or not env_truthy("BUTLER_WORKFLOW_QA_REPLAN", default=True):
        return graph

    snap = build_plan_snapshot(
        workflow.name,
        step_ids=[n.id for n in nodes],
        outcomes={sid: ("ok" if r.success else "fail") for sid, r in graph.nodes.items()},
    )
    update_step_outcome(snap, "qa", success=False, note=(qa.response or "")[:200])

    base_task = impl_node.config.task
    for attempt in range(1, max_replan + 1):
        impl_node.config.task = replan_implement_task(
            base_task,
            qa.response or "",
            attempt=attempt,
        )
        from butler.workflows.runner_ops import interpolate_var_pool_safe

        impl_node.config.task = interpolate_var_pool_safe(
            var_pool,
            impl_node.config.task,
        )
        impl_result = await orchestrator._run_with_retry(impl_node, on_progress=on_progress)
        graph.nodes["implement"] = impl_result
        update_step_outcome(snap, "implement", success=impl_result.success)
        if not impl_result.success:
            break
        qa_result = await orchestrator._run_with_retry(qa_node, on_progress=on_progress)
        graph.nodes["qa"] = qa_result
        update_step_outcome(snap, "qa", success=qa_result.success, note=(qa_result.response or "")[:200])
        qa = qa_result
        if qa_result.success and not qa_response_is_fail(qa_result.response or ""):
            graph.success = True
            break
        if not qa_response_is_fail(qa_result.response or ""):
            break
    from butler.workflows.runner_ops import current_audit_session_key_safe, record_plan_snapshot_safe

    sk = current_audit_session_key_safe(fallback="workflow")
    if sk:
        record_plan_snapshot_safe(sk, snap.to_json())
    return graph


def _rescue_spawn_configs(step: Any, *, session_key: str = "") -> list[AgentSpawnConfig]:
    from butler.model_resolve import workflow_step_spawn_model_config

    configs: list[AgentSpawnConfig] = []
    for rs in getattr(step, "rescue_steps", None) or []:
        model_cfg = workflow_step_spawn_model_config(rs.model)
        configs.append(
            AgentSpawnConfig(
                role=rs.role,
                task=rs.task,
                tools=rs.tools,
                model_config=model_cfg,
                session_key=session_key,
            )
        )
    return configs


def _workflow_progress_callback(
    workflow_name: str,
    total_steps: int,
    *,
    session_key: str = "",
    var_pool: Any = None,
    step_output_keys: dict[str, list[str]] | None = None,
    workspace: Any = None,
) -> Any:
    """Forward DAG step events to the gateway outbound bridge when present."""
    step_ids: list[str] = []
    completed_checkpoint: list[str] = []

    def _cb(step_id: str, phase: str, role: str, preview: str = "") -> None:
        del role
        from butler.gateway.outbound_bridge import get_gateway_bridge_optional

        bridge = get_gateway_bridge_optional()
        norm_phase = str(phase or "start").strip().lower()
        if norm_phase in ("failed", "fail", "error"):
            norm_phase = "fail"
        elif norm_phase in ("done", "ok", "success"):
            norm_phase = "done"
        else:
            norm_phase = "start"

        if norm_phase == "start" and step_id not in step_ids:
            step_ids.append(step_id)
        index = step_ids.index(step_id) + 1 if step_id in step_ids else len(step_ids)

        sk = str(session_key or "").strip()
        if sk:
            from butler.workflows.runner_ops import record_workflow_step_safe

            record_workflow_step_safe(
                sk,
                workflow=workflow_name,
                step_id=step_id,
                phase=norm_phase,
                step_index=index,
                step_total=total_steps,
            )
        if norm_phase == "done" and var_pool is not None and preview:
            keys = (step_output_keys or {}).get(step_id, ["output"])
            var_pool.set_step_output(step_id, preview, keys=keys)

        if norm_phase == "done" and step_id not in completed_checkpoint:
            completed_checkpoint.append(step_id)
            if workspace is not None:
                from pathlib import Path

                from butler.workflows.runner_ops import write_workflow_step_checkpoint_safe

                write_workflow_step_checkpoint_safe(
                    Path(workspace),
                    workflow_name,
                    step_id=step_id,
                    completed_steps=list(completed_checkpoint),
                    session_key=session_key,
                )
        if norm_phase == "fail" and preview:
            logger.warning(
                "Workflow %s step %s failed: %s",
                workflow_name,
                step_id,
                preview[:200],
            )
        if bridge is None:
            return
        bridge.notify_workflow_step(
            workflow_name,
            step_id,
            step_index=index,
            step_total=total_steps,
            phase=norm_phase,
        )

    return _cb


class WorkflowRunner:
    """Run a :class:`WorkflowDef` as a TaskOrchestrator DAG."""

    def __init__(self, orchestrator: Any | None = None) -> None:
        self._orchestrator = orchestrator
        self._tasks = TaskOrchestrator()

    def _orch(self) -> Any:
        if self._orchestrator is not None:
            return self._orchestrator
        from butler.execution_context import get_current_orchestrator
        from butler.orchestrator import ButlerOrchestrator

        orch = get_current_orchestrator()
        return orch if orch is not None else ButlerOrchestrator(user_id="owner", channel="workflow")

    def build_nodes(
        self,
        workflow: WorkflowDef,
        *,
        user_hint: str = "",
        session_key: str = "",
    ) -> list[TaskNode]:
        if not workflow.runnable:
            raise ValueError(
                f"工作流 '{workflow.name}' 没有可执行步骤；"
                "请在 project.yaml、.butler/workflows/ 或内置模板中定义 steps。"
            )

        hint_block = ""
        if user_hint.strip():
            hint_block = f"\n\n## 用户补充\n{user_hint.strip()}"

        from butler.model_resolve import workflow_step_spawn_model_config

        nodes: list[TaskNode] = []
        for step in workflow.steps:
            task_text = step.task.rstrip() + hint_block
            model_cfg = workflow_step_spawn_model_config(step.model)
            nodes.append(
                TaskNode(
                    id=step.id,
                    config=AgentSpawnConfig(
                        role=step.role,
                        task=task_text,
                        tools=step.tools,
                        model_config=model_cfg,
                        session_key=session_key,
                        clear_child_transcript=step.clear_child_transcript,
                    ),
                    depends_on=list(step.depends_on),
                    requires_approval=step.requires_approval,
                    max_retries=max(1, int(step.max_retries or 1)),
                    handoff_only=step.handoff_only,
                    clear_child_transcript=step.clear_child_transcript,
                    supervisor_note=step.supervisor_note,
                    optional=step.optional,
                    rescue_configs=_rescue_spawn_configs(step, session_key=session_key),
                    until=step.until,
                )
            )
        return nodes

    async def run_async(
        self,
        workflow: WorkflowDef,
        *,
        user_hint: str = "",
        session_key: str = "",
    ) -> TaskGraphResult:
        from butler.execution_context import use_execution_context

        from butler.workflows.variables import WorkflowVariablePool

        orch = self._orch()
        nodes = self.build_nodes(workflow, user_hint=user_hint, session_key=session_key)
        total_steps = len(nodes)
        var_pool = WorkflowVariablePool()
        output_keys = {s.id: list(s.output_keys) for s in workflow.steps}
        ws = None
        from butler.workflows.runner_ops import project_workspace_safe

        ws = project_workspace_safe(orch, session_key=session_key)
        progress_cb = _workflow_progress_callback(
            workflow.name,
            total_steps,
            session_key=session_key,
            var_pool=var_pool,
            step_output_keys=output_keys,
            workspace=ws,
        )
        needs_approval = any(n.requires_approval for n in nodes)

        def _on_approval(node: TaskNode) -> bool:
            from butler.human_gate import check_workflow_step_approval

            approved = check_workflow_step_approval(
                session_key or "workflow",
                workflow.name,
                node.id,
            )
            if not approved:
                from butler.workflows.runner_ops import save_workflow_pause_safe

                save_workflow_pause_safe(
                    workflow=workflow.name,
                    step_id=node.id,
                    session_key=session_key or "workflow",
                    execution_order=[n.id for n in nodes],
                )
            return approved

        from butler.execution_context import use_workflow_var_pool

        with use_execution_context(orch, session_key=session_key or "workflow"):
            with use_workflow_var_pool(var_pool):
                mp = workflow.max_parallel
                from butler.workflows.runner_ops import workflow_max_parallel_default_safe

                if mp is None:
                    default_mp = workflow_max_parallel_default_safe()
                    if default_mp is not None:
                        mp = default_mp
                graph = await self._tasks.execute_graph(
                    nodes,
                    on_progress=progress_cb,
                    on_approval=_on_approval if needs_approval else None,
                    max_parallel=mp,
                    serial=bool(workflow.serial),
                )
                graph = await _maybe_replan_dev_qa_loop(
                    workflow,
                    nodes,
                    graph,
                    orchestrator=self._tasks,
                    var_pool=var_pool,
                    on_progress=progress_cb,
                )
        self._cache_workflow_report(
            workflow,
            graph,
            session_key=session_key,
            orchestrator=orch,
        )
        from butler.workflows.runner_ops import write_workflow_run_snapshot_for_project_safe

        write_workflow_run_snapshot_for_project_safe(
            orch,
            workflow.name,
            graph,
            session_key=session_key,
        )
        if workflow.handlers:
            from pathlib import Path

            from butler.workflows.runner_ops import (
                project_workspace_safe,
                run_workflow_handlers_safe,
            )

            step_outcomes: dict[str, str] = {}
            for sid in graph.execution_order:
                result = graph.nodes.get(sid)
                if result is None:
                    continue
                step_outcomes[sid] = "ok" if result.success else "fail"
            ws_path = project_workspace_safe(orch, session_key=session_key)
            run_workflow_handlers_safe(
                workflow.handlers,
                workflow_name=workflow.name,
                session_key=session_key,
                workspace=Path(ws_path) if ws_path is not None else None,
                success=graph.success,
                summary=graph.error or "",
                step_outcomes=step_outcomes,
            )
        return graph

    def run(
        self,
        workflow: WorkflowDef,
        *,
        user_hint: str = "",
        session_key: str = "",
    ) -> TaskGraphResult:
        """Sync entry for gateway slash commands."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.run_async(workflow, user_hint=user_hint, session_key=session_key)
            )
        raise RuntimeError(
            "WorkflowRunner.run() cannot be called from a running event loop; "
            "use run_async() instead."
        )

    @staticmethod
    def _cache_workflow_report(
        workflow: WorkflowDef,
        graph: TaskGraphResult,
        *,
        session_key: str = "",
        orchestrator: Any | None = None,
    ) -> None:
        ok = sum(1 for r in graph.nodes.values() if r.success)
        total = len(graph.nodes)
        failed_steps: list[str] = []
        step_outcomes: dict[str, str] = {}
        summary_parts = []
        for step_id in graph.execution_order:
            result = graph.nodes.get(step_id)
            if result is None:
                continue
            if result.success:
                step_outcomes[step_id] = "ok"
                status = "OK"
            elif (result.error or "") == "workflow_step_approval_pending":
                step_outcomes[step_id] = "approval_pending"
                failed_steps.append(step_id)
                status = "WAIT"
            else:
                step_outcomes[step_id] = "fail"
                failed_steps.append(step_id)
                status = "FAIL"
            snippet = (result.response or result.error or "")[:400]
            if snippet == "workflow_step_approval_pending":
                snippet = "等待人工确认"
            summary_parts.append(f"[{step_id}] {status}: {snippet}")
        headline = (
            f"工作流 {workflow.name} 完成 ({ok}/{total} 步成功)"
            if graph.success
            else f"工作流 {workflow.name} 未完全成功 ({ok}/{total} 步)"
        )
        if any(v == "approval_pending" for v in step_outcomes.values()):
            headline += "（有待确认步骤）"
        if graph.error:
            summary_parts.append(f"图错误: {graph.error}")
        final_report = AgentReport(
            headline=headline,
            summary="\n".join(summary_parts),
            success=graph.success,
            task_preview=f"workflow:{workflow.name}"[:200],
            failed_steps=failed_steps,
            step_outcomes=step_outcomes,
        )
        from butler.report import (
            enrich_output_schema,
            enrich_report_decisions,
            maybe_repair_structured_output,
            render_structured_output_markdown,
        )

        enrich_report_decisions(final_report, "\n".join(summary_parts))
        steps = getattr(workflow, "steps", None) or []
        last_step = steps[-1] if steps else None
        if last_step and last_step.output_schema:
            last_result = graph.nodes.get(last_step.id) if last_step.id in graph.nodes else None
            text = ""
            if last_result is not None:
                text = last_result.response or ""
            enrich_output_schema(final_report, text, last_step.output_schema)
            final_report = maybe_repair_structured_output(
                final_report,
                text,
                last_step.output_schema,
                orchestrator=orchestrator,
            )
            md = render_structured_output_markdown(final_report.structured_output)
            if md:
                final_report.summary = (final_report.summary or "") + "\n\n" + md
        cache_report(final_report, session_key=session_key)
        if orchestrator is not None:
            proj = orchestrator.project_manager.get_current(session_key=session_key)
            if proj is not None:
                from pathlib import Path

                from butler.workflows.runner_ops import append_pending_outcome_safe

                append_pending_outcome_safe(
                    Path(proj.workspace),
                    project=str(proj.name or ""),
                    subject=f"workflow:{workflow.name}",
                    hypothesis=headline[:200],
                )

    @staticmethod
    def format_graph_summary(
        workflow: WorkflowDef,
        graph: TaskGraphResult,
        *,
        session_key: str = "",
    ) -> str:
        lines = [f"工作流「{workflow.name}」{'已完成' if graph.success else '未完全成功'}。"]
        for step_id in graph.execution_order:
            result = graph.nodes.get(step_id)
            if result is None:
                continue
            mark = "✓" if result.success else "✗"
            detail = (result.response or result.error or "").strip()
            if len(detail) > 280:
                detail = detail[:277] + "..."
            lines.append(f"{mark} {step_id}: {detail or '(无输出)'}")
        if graph.error:
            lines.append(f"备注: {graph.error}")
        if any(
            (graph.nodes.get(sid) and (graph.nodes[sid].error or "") == "workflow_step_approval_pending")
            for sid in graph.execution_order
        ):
            from butler.human_gate import format_pending_hint

            hint = format_pending_hint(session_key)
            if hint:
                lines.append(hint)
        lines.append("回复「/详细」查看结构化报告。")
        return "\n".join(lines)


def run_workflow_for_project(
    project: Any,
    name: str,
    *,
    user_hint: str = "",
    session_key: str = "",
    orchestrator: Any | None = None,
) -> str:
    """Resolve and run a workflow; return user-facing text."""
    from butler.workflows.loader import resolve_workflow

    wf = resolve_workflow(project, name)
    if wf is None:
        return f"未找到工作流: {name}"
    if not wf.runnable:
        return (
            f"工作流「{name}」已登记但缺少步骤定义。"
            "请在 project.yaml 添加 steps，或提供 .butler/workflows/{name}.yaml。"
        )
    runner = WorkflowRunner(orchestrator=orchestrator)
    graph = runner.run(wf, user_hint=user_hint, session_key=session_key)
    return runner.format_graph_summary(wf, graph, session_key=session_key)


__all__ = ["WorkflowRunner", "run_workflow_for_project"]
