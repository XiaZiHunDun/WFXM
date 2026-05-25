"""Execute project workflows through :class:`~butler.task_orchestrator.TaskOrchestrator`."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from butler.report import AgentReport, cache_report
from butler.task_orchestrator import AgentSpawnConfig, TaskNode, TaskGraphResult, TaskOrchestrator
from butler.workflows.schema import WorkflowDef

logger = logging.getLogger(__name__)


def _workflow_progress_callback(
    workflow_name: str,
    total_steps: int,
    *,
    session_key: str = "",
    var_pool: Any = None,
    step_output_keys: dict[str, list[str]] | None = None,

) -> Any:
    """Forward DAG step events to the gateway outbound bridge when present."""
    step_ids: list[str] = []

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
            try:
                from butler.core.session_transcript import record_workflow_step

                record_workflow_step(
                    sk,
                    workflow=workflow_name,
                    step_id=step_id,
                    phase=norm_phase,
                    step_index=index,
                    step_total=total_steps,
                )
            except Exception:
                pass

        if norm_phase == "done" and var_pool is not None and preview:
            keys = (step_output_keys or {}).get(step_id, ["output"])
            var_pool.set_step_output(step_id, preview, keys=keys)

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
                    ),
                    depends_on=list(step.depends_on),
                    requires_approval=step.requires_approval,
                    max_retries=max(1, int(step.max_retries or 1)),
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
        progress_cb = _workflow_progress_callback(
            workflow.name,
            total_steps,
            session_key=session_key,
            var_pool=var_pool,
            step_output_keys=output_keys,
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
                try:
                    from butler.workflows.pause_state import WorkflowPauseState, save_workflow_pause

                    save_workflow_pause(
                        WorkflowPauseState(
                            workflow=workflow.name,
                            step_id=node.id,
                            session_key=session_key or "workflow",
                            execution_order=[n.id for n in nodes],
                            completed_steps=[],
                        ),
                    )
                except Exception:
                    pass
            return approved

        from butler.execution_context import use_execution_context, use_workflow_var_pool

        with use_execution_context(orch, session_key=session_key or "workflow"):
            with use_workflow_var_pool(var_pool):
                graph = await self._tasks.execute_graph(
                    nodes,
                    on_progress=progress_cb,
                    on_approval=_on_approval if needs_approval else None,
                )
        self._cache_workflow_report(workflow, graph, session_key=session_key)
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
            loop = asyncio.get_running_loop()
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
        cache_report(
            AgentReport(
                headline=headline,
                summary="\n".join(summary_parts),
                success=graph.success,
                task_preview=f"workflow:{workflow.name}"[:200],
                failed_steps=failed_steps,
                step_outcomes=step_outcomes,
            ),
            session_key=session_key,
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
