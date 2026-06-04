from __future__ import annotations

from unittest.mock import MagicMock

from butler.execution_context import (
    get_audit_session_key,
    get_current_orchestrator,
    get_current_session_key,
    use_execution_context,
)


def test_execution_context_restores_previous_values():
    outer = MagicMock(name="outer")  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    inner = MagicMock(name="inner")  # noqa: magicmock-no-spec — complex facade, spec= 收益低

    assert get_current_orchestrator() is None
    assert get_current_session_key() == ""

    with use_execution_context(outer, session_key="outer-session"):
        assert get_current_orchestrator() is outer
        assert get_current_session_key() == "outer-session"

        with use_execution_context(inner, session_key="inner-session"):
            assert get_current_orchestrator() is inner
            assert get_current_session_key() == "inner-session"

        assert get_current_orchestrator() is outer
        assert get_current_session_key() == "outer-session"

    assert get_current_orchestrator() is None
    assert get_current_session_key() == ""


def test_use_execution_context_can_bind_session_without_orchestrator():
    with use_execution_context(session_key="task:abc123"):
        assert get_current_orchestrator() is None
        assert get_current_session_key() == "task:abc123"


def test_get_audit_session_key_uses_fallback_when_unbound():
    assert get_audit_session_key() == "unscoped"
    with use_execution_context(session_key="sess-1"):
        assert get_audit_session_key() == "sess-1"


def test_get_audit_session_key_allows_empty_when_orchestrator_bound():
    orch = MagicMock(name="orch")  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    with use_execution_context(orch):
        assert get_audit_session_key() == ""
