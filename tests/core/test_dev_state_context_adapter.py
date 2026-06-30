"""Unit tests for DevEngine state ACL adapter."""

from __future__ import annotations

from butler.core.dev_state_context_adapter import (
    dev_engine_dict_to_view,
    loop_dev_state_view_to_payload,
    to_loop_dev_state_view,
)
from butler.dev_engine.dev_loop import create_dev_state, transition
from butler.dev_engine.dev_state import DevPhase, VerifyResult, VerifyStatus


def test_dev_state_object_passthrough():
    state = create_dev_state("task")
    transition(state, "verify_pass", verify_result=VerifyResult(status=VerifyStatus.PASS))
    view = to_loop_dev_state_view(state, source="test")
    assert view.phase == "DONE"
    assert view.verify_passed is True
    assert view.edits == 0


def test_dict_legacy_verify_shape():
    view = to_loop_dev_state_view(
        {
            "phase": "done",
            "edits": 2,
            "fixes": 1,
            "iterations": 4,
            "verify": {"status": "PASS"},
        },
        source="delegate",
    )
    assert view.phase == "DONE"
    assert view.verify_passed is True
    assert view.edits == 2
    assert view.is_terminal is True


def test_dict_review_nested_shape():
    view = to_loop_dev_state_view(
        {
            "phase": "REVIEW",
            "review": {"passed": False, "findings_count": 3},
            "verify_passed": True,
        },
        source="gate",
    )
    assert view.review_passed is False
    assert view.verify_passed is True


def test_loop_dev_state_view_to_payload_roundtrip():
    view = to_loop_dev_state_view(
        {"phase": "FIX", "edits": 1, "verify_passed": False},
        source="attach",
    )
    payload = loop_dev_state_view_to_payload(view)
    assert payload["phase"] == "FIX"
    assert payload["verify_passed"] is False
    assert payload["dev_state_view_version"] == "v1"


def test_dev_engine_dict_to_view_empty():
    view = dev_engine_dict_to_view(None, source="x")
    assert view.phase == "PLAN"
    assert view.metadata.get("acl_empty") is True


def test_delegate_gate_view_from_payload():
    view = dev_engine_dict_to_view(
        {"edits": 2, "verify_passed": False, "verify_output_tail": "E   assert"},
        source="verify_gate",
    )
    assert view.edits == 2
    assert view.verify_passed is False
