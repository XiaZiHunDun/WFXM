"""Unit tests for compaction ACL adapter."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.contracts.compaction_ports import LoopCompactionView
from butler.core.compaction_context_adapter import (
    adapt_hook_contexts,
    apply_compaction_view_to_diagnostics,
    to_loop_compaction_view,
)


@pytest.mark.unit
def test_str_input():
    view = to_loop_compaction_view("  hello  ", source="test")
    assert view.content == "hello"
    assert view.schema_version == "v1"
    assert view.metadata["acl_shape"] == "str"


@pytest.mark.unit
def test_none_input():
    view = to_loop_compaction_view(None, source="test")
    assert view.content == ""
    assert view.metadata.get("acl_empty") is True


@pytest.mark.unit
def test_v1_raw_dict():
    view = to_loop_compaction_view({"raw": "legacy body"}, source="test")
    assert view.content == "legacy body"
    assert view.metadata["acl_shape"] == "v1_raw"


@pytest.mark.unit
def test_v2_summary_tags():
    view = to_loop_compaction_view(
        {"summary": "摘要", "tags": ["api", "gateway"]},
        source="test",
    )
    assert "摘要" in view.content
    assert "api" in view.content
    assert view.metadata["acl_shape"] == "v2_summary_tags"


@pytest.mark.unit
def test_v2_summary_no_tags():
    view = to_loop_compaction_view({"summary": "only summary"}, source="test")
    assert view.content == "only summary"


@pytest.mark.unit
def test_hook_additional_context_list():
    view = to_loop_compaction_view(
        {"additionalContext": ["line1", "line2"]},
        source="hook",
    )
    assert "line1" in view.content
    assert "line2" in view.content
    assert view.metadata["acl_shape"] == "hook_additional_context"


@pytest.mark.unit
def test_hook_additional_context_snake_case():
    view = to_loop_compaction_view(
        {"additional_context": "snake ctx"},
        source="hook",
    )
    assert view.content == "snake ctx"


@pytest.mark.unit
def test_unknown_dict_warns():
    view = to_loop_compaction_view({"foo": "bar"}, source="test")
    assert view.metadata.get("acl_warn") == "unknown_shape"


@pytest.mark.unit
def test_passthrough_loop_compaction_view():
    original = LoopCompactionView(content="x", metadata={"k": 1})
    assert to_loop_compaction_view(original, source="test") is original


@pytest.mark.unit
def test_non_dict_non_str_fallback():
    view = to_loop_compaction_view(12345, source="test")
    assert view.content == "12345"


@pytest.mark.unit
@patch("butler.core.compaction_context_adapter._adapt_known_shape", side_effect=RuntimeError("boom"))
def test_degraded_on_exception(_mock):
    view = to_loop_compaction_view({"summary": "x"}, source="fail")
    assert view.metadata.get("acl_degraded") is True
    assert "异常" in view.content


@pytest.mark.unit
def test_apply_compaction_view_to_diagnostics():
    diag: dict = {}
    view = LoopCompactionView(
        content="c",
        metadata={"acl_shape": "v2_summary_tags", "acl_warn": "unknown_shape"},
    )
    apply_compaction_view_to_diagnostics(view, diag)
    assert diag["compaction_view_version"] == "v1"
    assert diag["compaction_acl_shape"] == "v2_summary_tags"
    assert diag["compaction_acl_degraded"] is True


@pytest.mark.unit
def test_adapt_hook_contexts_joins():
    out = adapt_hook_contexts(["a", "b"], source="post_compact_hook")
    assert out == "a\nb"


@pytest.mark.unit
def test_empty_tags_list():
    view = to_loop_compaction_view({"summary": "s", "tags": []}, source="test")
    assert view.content == "s"
