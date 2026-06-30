"""Unit tests for hook context ACL adapter."""

from __future__ import annotations

from butler.contracts.hook_context_ports import HookContextView
from butler.core.hook_context_adapter import (
    adapt_hook_context_lines,
    apply_hook_context_to_diagnostics,
    to_hook_context_view,
)


def test_hook_str_shape():
    view = to_hook_context_view("  hello  ", source="test")
    assert view.content == "hello"
    assert view.metadata.get("acl_shape") == "str"


def test_hook_v2_summary_tags():
    view = to_hook_context_view(
        {"summary": "摘要", "tags": ["a", "b"]},
        source="test",
    )
    assert "摘要" in view.content
    assert "标签" in view.content


def test_adapt_hook_context_lines_joins():
    text = adapt_hook_context_lines(
        ['{"summary": "one"}', "plain"],
        source="test",
    )
    assert "one" in text
    assert "plain" in text


def test_apply_hook_context_to_diagnostics():
    view = HookContextView(
        content="x",
        metadata={"acl_shape": "str"},
    )
    diag: dict = {}
    apply_hook_context_to_diagnostics(view, diag)
    assert diag["hook_context_view_version"] == "v1"
    assert diag["hook_acl_shape"] == "str"


def test_hook_additional_context_dict():
    view = to_hook_context_view(
        {"additionalContext": ["line1", "line2"]},
        source="hook",
    )
    assert "line1" in view.content
    assert view.metadata.get("acl_shape") == "hook_additional_context"
