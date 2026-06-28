"""Tests for butler.dag_scheduler (ENG-4)."""

from __future__ import annotations

import pytest

from butler.dag_scheduler import group_into_layers, prepare_layer_node, split_layer_batches, topological_sort
from butler.task_orchestrator import AgentResult, AgentSpawnConfig, TaskNode


def _node(nid: str, *deps: str, **kw) -> TaskNode:
    return TaskNode(
        id=nid,
        config=AgentSpawnConfig(role="r", task="t"),
        depends_on=list(deps),
        **kw,
    )


def test_topological_sort_linear():
    nodes = [_node("a"), _node("b", "a"), _node("c", "b")]
    assert topological_sort(nodes) == ["a", "b", "c"]


def test_group_into_layers():
    nodes = [_node("a"), _node("b", "a"), _node("c", "a"), _node("d", "b", "c")]
    order = topological_sort(nodes)
    layers = group_into_layers(order, {n.id: n for n in nodes})
    assert layers[0] == ["a"]
    assert set(layers[1]) == {"b", "c"}
    assert layers[2] == ["d"]


def test_topological_sort_cycle_raises():
    nodes = [_node("a", "b"), _node("b", "a")]
    with pytest.raises(ValueError, match="cycle"):
        topological_sort(nodes)


def test_prepare_layer_node_injects_dependency_context():
    nodes = [_node("a"), _node("b", "a")]
    node_map = {n.id: n for n in nodes}
    completed = {
        "a": AgentResult(success=True, response="hello from a"),
    }
    skip = prepare_layer_node(
        node_map["b"],
        completed=completed,
        cancelled=set(),
        node_map=node_map,
        on_approval=None,
    )
    assert skip is None
    assert "[a 结果]" in (node_map["b"].config.context or "")


def test_prepare_layer_node_skips_failed_dependency():
    nodes = [_node("a"), _node("b", "a")]
    node_map = {n.id: n for n in nodes}
    completed = {"a": AgentResult(success=False, error="boom")}
    skip = prepare_layer_node(
        node_map["b"],
        completed=completed,
        cancelled=set(),
        node_map=node_map,
        on_approval=None,
    )
    assert skip is not None
    assert skip.success is False
    assert "failed dependency" in (skip.error or "")


def test_split_layer_batches_respects_max_parallel():
    tasks = [("a", _node("a")), ("b", _node("b")), ("c", _node("c"))]
    batches = split_layer_batches(tasks, serial=False, max_parallel=2)
    assert len(batches) == 2
    assert len(batches[0]) == 2
    assert len(batches[1]) == 1
