"""Unit tests for memory prefetch ACL adapter."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.contracts.memory_ports import LoopMemoryView
from butler.core.memory_context_adapter import (
    adapt_memory_prefetch_content,
    apply_memory_view_to_diagnostics,
    to_loop_memory_view,
)


@pytest.mark.unit
def test_str_input():
    view = to_loop_memory_view("  hello  ", source="test")
    assert view.content == "hello"
    assert view.metadata["acl_shape"] == "str"


@pytest.mark.unit
def test_chunks_dict():
    view = to_loop_memory_view(
        {"chunks": ["a", "b"], "snippets": ["s1"]},
        source="test",
    )
    assert "a" in view.content
    assert "b" in view.content
    assert view.metadata["acl_shape"] == "v1_chunks"


@pytest.mark.unit
def test_content_key_dict():
    view = to_loop_memory_view({"content": "body"}, source="test")
    assert view.content == "body"
    assert view.metadata["acl_shape"] == "v1_content"


@pytest.mark.unit
def test_list_input():
    view = to_loop_memory_view(["line1", "line2"], source="test")
    assert "line1" in view.content
    assert view.metadata["acl_shape"] == "list"


@pytest.mark.unit
def test_adapt_never_raises():
    with patch(
        "butler.core.memory_context_adapter_ops._adapt_known_shape",
        side_effect=RuntimeError("boom"),
    ):
        view = to_loop_memory_view({"x": 1}, source="test")
    assert view.content == ""
    assert view.metadata.get("acl_degraded") is True


@pytest.mark.unit
def test_apply_diagnostics():
    diag: dict = {}
    apply_memory_view_to_diagnostics(
        LoopMemoryView(content="x", metadata={"acl_shape": "str", "acl_warn": "w"}),
        diag,
    )
    assert diag["memory_view_version"] == "v1"
    assert diag["memory_acl_shape"] == "str"
    assert diag["memory_acl_degraded"] is True


@pytest.mark.unit
def test_adapt_memory_prefetch_content():
    out = adapt_memory_prefetch_content({"text": "memo"}, diagnostics={})
    assert out == "memo"
