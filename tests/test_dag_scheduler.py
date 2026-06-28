"""Tests for butler.dag_scheduler (ENG-4)."""

from __future__ import annotations

import pytest

from butler.dag_scheduler import group_into_layers, topological_sort
from butler.task_orchestrator import TaskNode


def _node(nid: str, *deps: str) -> TaskNode:
    from butler.task_orchestrator import AgentSpawnConfig

    return TaskNode(id=nid, config=AgentSpawnConfig(role="r", task="t"), depends_on=list(deps))


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
