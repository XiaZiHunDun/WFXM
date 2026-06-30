"""Unit tests for API message boundary ACL adapter."""

from __future__ import annotations

import pytest

from butler.core.message_context_adapter import (
    annotate_api_message_boundary,
    api_message_acl_enabled,
    to_loop_api_message_view,
)


@pytest.mark.unit
def test_str_content_message():
    view = to_loop_api_message_view({"role": "user", "content": "hi"}, source="test")
    assert view.role == "user"
    assert view.content == "hi"
    assert view.metadata["acl_shape"] == "str"


@pytest.mark.unit
def test_list_blocks_content():
    view = to_loop_api_message_view(
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "hello"}],
        },
        source="test",
    )
    assert view.content == "hello"
    assert view.metadata["acl_shape"] == "list_blocks"


@pytest.mark.unit
def test_invalid_role_degrades():
    view = to_loop_api_message_view({"role": "nope", "content": "x"}, source="test")
    assert view.metadata.get("acl_degraded") is True


@pytest.mark.unit
def test_annotate_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BUTLER_API_MESSAGE_ACL", raising=False)
    diag: dict = {}
    annotate_api_message_boundary([{"role": "user", "content": "a"}], diag)
    assert "api_message_acl_checked" not in diag


@pytest.mark.unit
def test_annotate_when_enabled(monkeypatch):
    monkeypatch.setenv("BUTLER_API_MESSAGE_ACL", "1")
    assert api_message_acl_enabled()
    diag: dict = {}
    annotate_api_message_boundary(
        [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
        diag,
    )
    assert diag.get("api_message_acl_checked") is True
    assert diag.get("api_message_acl_count") == 2
