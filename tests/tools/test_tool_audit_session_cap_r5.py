"""R5-6: tool_audit session bucket cap."""

from __future__ import annotations

import pytest

from butler.execution_context import use_execution_context
from butler.tools import tool_audit as ta


@pytest.fixture(autouse=True)
def _reset():
    ta.reset_tool_audit_events()
    yield
    ta.reset_tool_audit_events()


@pytest.mark.unit
def test_session_bucket_cap(monkeypatch):
    monkeypatch.setattr(ta, "_MAX_SESSION_BUCKETS", 4)
    for i in range(6):
        with use_execution_context(session_key=f"sess-{i}"):
            ta.finalize_tool_result("memo", {}, {"ok": True, "i": i})
    with ta._TOOL_AUDIT_LOCK:
        assert len(ta._TOOL_AUDIT_EVENTS_BY_SESSION) <= 4
