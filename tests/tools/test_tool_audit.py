"""R6-2: unit tests for butler.tools.tool_audit."""

from __future__ import annotations

import json

import pytest

from butler.execution_context import use_execution_context
from butler.tools.tool_audit import (
    finalize_tool_result,
    get_tool_audit_events,
    pop_last_tool_audit_for_tool,
    reset_tool_audit_events,
)


@pytest.fixture(autouse=True)
def _clear_audit():
    reset_tool_audit_events()
    yield
    reset_tool_audit_events()


@pytest.mark.unit
class TestFinalizeToolResult:
    def test_dict_success_envelope_and_audit(self):
        out = finalize_tool_result(
            "read_file",
            {"path": "a.txt"},
            {"ok": True, "content": "hello"},
        )
        data = json.loads(out)
        assert data["ok"] is True
        event = get_tool_audit_events()[-1]
        assert event["tool"] == "read_file"
        assert event["ok"] is True
        assert event["code"] == "TOOL_OK"
        assert event["arg_keys"] == ["path"]

    def test_plain_text_success_passthrough(self):
        out = finalize_tool_result("skills_list", {}, "skill-a\nskill-b")
        assert "skill-a" in out
        event = get_tool_audit_events()[-1]
        assert event["code"] == "TOOL_OK"

    def test_guardrail_halt_code(self):
        out = finalize_tool_result(
            "terminal",
            {"command": "rm -rf /"},
            {"ok": False, "guardrail": {"action": "halt"}, "error": "blocked"},
        )
        data = json.loads(out)
        assert data["code"] == "TOOL_GUARDRAIL_HALT"
        assert get_tool_audit_events()[-1]["code"] == "TOOL_GUARDRAIL_HALT"

    def test_unknown_tool_error_code(self):
        out = finalize_tool_result(
            "missing_tool",
            {},
            {"error": "Unknown tool: missing_tool", "ok": False},
        )
        data = json.loads(out)
        assert data["code"] == "TOOL_NOT_FOUND"

    def test_security_denial_code(self):
        from butler.tools.registry import _ensure_builtins

        _ensure_builtins()
        out = finalize_tool_result(
            "read_file",
            {"path": "/etc/passwd"},
            {"ok": False, "error": "Access denied: outside workspace"},
        )
        data = json.loads(out)
        assert data["code"] == "TOOL_SECURITY_DENIED"

    def test_records_session_key(self):
        with use_execution_context(session_key="audit-sess"):
            finalize_tool_result("memo", {"text": "hi"}, {"ok": True})
        scoped = get_tool_audit_events(session_key="audit-sess")
        assert len(scoped) == 1
        assert scoped[0]["session_key"] == "audit-sess"


@pytest.mark.unit
class TestToolAuditHelpers:
    def test_reset_scoped_session_only(self):
        with use_execution_context(session_key="keep"):
            finalize_tool_result("memo", {}, {"ok": True})
        with use_execution_context(session_key="drop"):
            finalize_tool_result("memo", {}, {"ok": True})
        reset_tool_audit_events("drop")
        assert get_tool_audit_events(session_key="drop") == []
        assert len(get_tool_audit_events(session_key="keep")) == 1

    def test_pop_last_tool_audit_for_tool(self):
        finalize_tool_result("read_file", {}, {"ok": True})
        finalize_tool_result("write_file", {}, {"ok": True})
        pop_last_tool_audit_for_tool("write_file")
        events = get_tool_audit_events()
        assert len(events) == 1
        assert events[0]["tool"] == "read_file"

    def test_get_tool_audit_events_limit(self):
        for i in range(5):
            finalize_tool_result("memo", {"i": i}, {"ok": True, "n": i})
        tail = get_tool_audit_events(limit=2)
        assert len(tail) == 2
        assert tail[-1]["arg_keys"] == ["i"]
