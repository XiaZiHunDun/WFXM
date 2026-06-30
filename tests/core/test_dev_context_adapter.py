"""Unit tests for DevEngine verify ACL adapter."""

from __future__ import annotations

from butler.core.dev_context_adapter import (
    apply_dev_verify_view_to_state,
    to_dev_verify_view,
    to_verify_result,
)
from butler.dev_engine.dev_loop import create_dev_state, transition
from butler.dev_engine.dev_state import DiagSeverity, Diagnostic, VerifyResult, VerifyStatus


def test_verify_result_passthrough():
    vr = VerifyResult(status=VerifyStatus.FAIL, output_tail="err")
    view = to_dev_verify_view(vr, source="test")
    assert view.status == "FAIL"
    out = to_verify_result(vr, source="test")
    assert out.status == VerifyStatus.FAIL


def test_dict_verify_shape():
    view = to_dev_verify_view(
        {
            "status": "fail",
            "diagnostics": [
                {"file": "a.py", "line": 1, "message": "syntax", "severity": "error"},
            ],
            "output_tail": "boom",
        },
        source="tool",
    )
    assert view.status == "FAIL"
    vr = to_verify_result(view, source="tool")
    assert vr.error_count == 1
    assert vr.output_tail == "boom"


def test_transition_verify_fail_with_dict():
    state = create_dev_state("task")
    transition(
        state,
        "verify_fail",
        verify_result={
            "status": "FAIL",
            "diagnostics": [{"file": "x", "line": 2, "message": "e", "severity": "error"}],
        },
    )
    assert state.verify_result.status == VerifyStatus.FAIL
    assert len(state.diagnostics) == 1
    bag = getattr(state, "_acl_metadata", {})
    assert bag.get("dev_verify_view_version") == "v1"


def test_apply_dev_verify_view_degraded_flag():
    state = create_dev_state()
    view = to_dev_verify_view({"weird": True}, source="x")
    apply_dev_verify_view_to_state(view, state)
    bag = getattr(state, "_acl_metadata", {})
    assert bag.get("dev_acl_shape") in ("dict", "fallback_str", "unknown_dict")


def test_verify_result_object_in_transition():
    state = create_dev_state()
    vr = VerifyResult(
        status=VerifyStatus.FAIL,
        diagnostics=[
            Diagnostic(file="f.py", line=3, severity=DiagSeverity.ERROR, message="m"),
        ],
    )
    transition(state, "verify_fail", verify_result=vr)
    assert state.verify_result.error_count == 1
