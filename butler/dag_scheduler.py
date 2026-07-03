"""DAG topology helpers extracted from ``TaskOrchestrator.execute_graph`` (ENG-4)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.task_orchestrator import AgentResult, TaskNode


def topological_sort(nodes: list["TaskNode"]) -> list[str]:
    """Kahn's algorithm for topological ordering."""
    graph: dict[str, list[str]] = {n.id: [] for n in nodes}
    in_degree: dict[str, int] = {n.id: 0 for n in nodes}

    for n in nodes:
        for dep in n.depends_on:
            if dep in graph:
                graph[dep].append(n.id)
                in_degree[n.id] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    result: list[str] = []

    while queue:
        nid = queue.pop(0)
        result.append(nid)
        for neighbor in graph.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(nodes):
        raise ValueError("Task graph contains a cycle")

    return result


def group_into_layers(order: list[str], node_map: dict[str, "TaskNode"]) -> list[list[str]]:
    """Group topologically sorted nodes into parallel layers."""
    depth: dict[str, int] = {}
    for nid in order:
        node = node_map[nid]
        if not node.depends_on:
            depth[nid] = 0
        else:
            depth[nid] = max(depth.get(d, 0) for d in node.depends_on) + 1

    max_depth = max(depth.values()) if depth else 0
    layers: list[list[str]] = [[] for _ in range(max_depth + 1)]
    for nid in order:
        layers[depth[nid]].append(nid)

    return [layer for layer in layers if layer]


def first_cancelled_dependency(node: "TaskNode", cancelled: set[str]) -> str:
    for dep_id in node.depends_on:
        if dep_id in cancelled:
            return str(dep_id)
    return ""


def direct_dependents(node_map: dict[str, "TaskNode"], parent_id: str) -> list["TaskNode"]:
    return [node for node in node_map.values() if parent_id in node.depends_on]


def cancel_direct_dependents(
    node_map: dict[str, "TaskNode"],
    parent_id: str,
    cancelled: set[str],
) -> None:
    for child in direct_dependents(node_map, parent_id):
        cancelled.add(child.id)


def first_failed_dependency(
    node: "TaskNode",
    completed: dict[str, "AgentResult"],
    node_map: dict[str, "TaskNode"],
) -> str:
    from butler.core.workflow_flags import workflow_optional_enabled

    for dep_id in node.depends_on:
        dep_result = completed.get(dep_id)
        if dep_result is not None and not dep_result.success:
            dep_node = node_map.get(dep_id)
            if (
                workflow_optional_enabled()
                and dep_node is not None
                and dep_node.optional
            ):
                continue
            return str(dep_id)
    return ""


def graph_all_required_ok(
    completed: dict[str, "AgentResult"],
    node_map: dict[str, "TaskNode"],
) -> bool:
    from butler.core.workflow_flags import workflow_optional_enabled

    for nid, result in completed.items():
        node = node_map.get(nid)
        if result.success:
            continue
        if workflow_optional_enabled() and node is not None and node.optional:
            continue
        return False
    return True


def format_dependency_context(
    dep_id: str,
    dep_result: "AgentResult",
    *,
    handoff_only: bool,
) -> str:
    if handoff_only and dep_result.report is not None:
        from butler.core.handoff import render_handoff_block

        rep = dep_result.report
        return str(render_handoff_block(
            from_role=dep_id,
            to_role="",
            current_state=(rep.summary or dep_result.response or "")[:400],
            deliverable=rep.headline or dep_id,
            prior_report=rep,
        ))
    text = (dep_result.response or dep_result.error or "").strip()
    if not text:
        return ""
    return f"[{dep_id} 结果]: {text[:1500]}"


def inject_dependency_context(
    node: "TaskNode",
    completed: dict[str, "AgentResult"],
) -> None:
    if not node.depends_on:
        return
    dep_contexts: list[str] = []
    for dep_id in node.depends_on:
        dep_result = completed.get(dep_id)
        if dep_result is None:
            continue
        block = format_dependency_context(
            dep_id,
            dep_result,
            handoff_only=node.handoff_only,
        )
        if block:
            dep_contexts.append(block)
    if dep_contexts:
        node.config.context = (
            (node.config.context or "") + "\n\n" + "\n".join(dep_contexts)
        )


def inject_supervisor_note(node: "TaskNode") -> None:
    if not node.supervisor_note.strip():
        return
    sup = f"## Supervisor 指令\n{node.supervisor_note.strip()[:600]}"
    node.config.context = ((node.config.context or "") + "\n\n" + sup).strip()


def prepare_layer_node(
    node: "TaskNode",
    *,
    completed: dict[str, "AgentResult"],
    cancelled: set[str],
    node_map: dict[str, "TaskNode"],
    on_approval: Callable[["TaskNode"], bool] | None,
) -> "AgentResult | None":
    """Return a skip result, or ``None`` if the node is ready to execute."""
    from butler.task_orchestrator import AgentResult

    cancelled_dep = first_cancelled_dependency(node, cancelled)
    if cancelled_dep:
        return AgentResult(
            success=False,
            error=f"Skipped due to cancelled dependency: {cancelled_dep}",
        )

    failed_dep = first_failed_dependency(node, completed, node_map)
    if failed_dep:
        return AgentResult(
            success=False,
            error=f"Skipped due to failed dependency: {failed_dep}",
        )

    inject_dependency_context(node, completed)
    inject_supervisor_note(node)

    if node.requires_approval:
        if on_approval is None or not on_approval(node):
            return AgentResult(success=False, error="workflow_step_approval_pending")

    return None


def split_layer_batches(
    layer_tasks: list[tuple[str, "TaskNode"]],
    *,
    serial: bool,
    max_parallel: int | None,
) -> list[list[tuple[str, "TaskNode"]]]:
    if serial:
        return [[item] for item in layer_tasks]
    if max_parallel and max_parallel > 0:
        return [
            layer_tasks[i : i + max_parallel]
            for i in range(0, len(layer_tasks), max_parallel)
        ]
    return [layer_tasks]


def apply_node_router(
    nid: str,
    node: "TaskNode",
    result: "AgentResult",
    *,
    node_map: dict[str, "TaskNode"],
    cancelled: set[str],
) -> list[str]:
    """Apply optional router; return human-readable error strings."""
    if not node.router or not result.success:
        return []
    errors: list[str] = []
    from butler.dag_scheduler_ops import run_node_router_safe

    next_id, router_error = run_node_router_safe(node.router, result)
    if router_error:
        errors.append(f"Router for {nid!r} failed: {router_error}")
        cancel_direct_dependents(node_map, nid, cancelled)
        return errors
    if not next_id:
        return errors
    if next_id not in node_map:
        errors.append(f"Router for {nid!r} returned unknown target {next_id!r}")
        cancel_direct_dependents(node_map, nid, cancelled)
        return errors
    deps = direct_dependents(node_map, nid)
    if next_id not in {dependent.id for dependent in deps}:
        errors.append(
            f"Router for {nid!r} returned non-direct dependent {next_id!r}"
        )
        cancel_direct_dependents(node_map, nid, cancelled)
        return errors
    for dependent in deps:
        if dependent.id != next_id:
            cancelled.add(dependent.id)
    return errors


def finalize_unexecuted_nodes(
    order: list[str],
    *,
    completed: dict[str, "AgentResult"],
    cancelled: set[str],
    node_map: dict[str, "TaskNode"],
    errors: list[str],
) -> None:
    from butler.task_orchestrator import AgentResult

    for node_id in order:
        if node_id in completed or node_id in cancelled:
            continue
        cancelled_dep = first_cancelled_dependency(node_map[node_id], cancelled)
        if cancelled_dep:
            completed[node_id] = AgentResult(
                success=False,
                error=f"Skipped due to cancelled dependency: {cancelled_dep}",
            )
        else:
            errors.append(f"Node {node_id!r} was not executed")


__all__ = [
    "apply_node_router",
    "cancel_direct_dependents",
    "direct_dependents",
    "finalize_unexecuted_nodes",
    "first_cancelled_dependency",
    "first_failed_dependency",
    "format_dependency_context",
    "graph_all_required_ok",
    "group_into_layers",
    "inject_dependency_context",
    "inject_supervisor_note",
    "prepare_layer_node",
    "split_layer_batches",
    "topological_sort",
]
