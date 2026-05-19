from __future__ import annotations

from unittest.mock import MagicMock

from butler.execution_context import (
    get_current_orchestrator,
    get_current_session_key,
    use_execution_context,
)


def test_execution_context_restores_previous_values():
    outer = MagicMock(name="outer")
    inner = MagicMock(name="inner")

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
