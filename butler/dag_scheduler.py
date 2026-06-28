"""DAG topology helpers extracted from ``TaskOrchestrator.execute_graph`` (ENG-4)."""

from __future__ import annotations

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
            return dep_id
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
            return dep_id
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
        return render_handoff_block(
            from_role=dep_id,
            to_role="",
            current_state=(rep.summary or dep_result.response or "")[:400],
            deliverable=rep.headline or dep_id,
            prior_report=rep,
        )
    text = (dep_result.response or dep_result.error or "").strip()
    if not text:
        return ""
    return f"[{dep_id} 结果]: {text[:1500]}"


__all__ = [
    "cancel_direct_dependents",
    "direct_dependents",
    "first_cancelled_dependency",
    "first_failed_dependency",
    "format_dependency_context",
    "graph_all_required_ok",
    "group_into_layers",
    "topological_sort",
]
