"""Unit tests for dev review ACL adapter."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.contracts.review_ports import DevReviewView, ReviewFinding
from butler.core.review_context_adapter import (
    apply_dev_review_view_to_diagnostics,
    max_severity,
    merge_review_views,
    parse_llm_review_text,
    review_text_passed,
    to_dev_review_view,
)


@pytest.mark.unit
def test_dict_findings():
    view = to_dev_review_view(
        {
            "passed": False,
            "findings": [
                {"severity": "error", "rule_id": "RK-SIZE", "message": "too long"},
            ],
        },
        source="test",
    )
    assert view.passed is False
    assert view.findings[0].rule_id == "RK-SIZE"


@pytest.mark.unit
def test_llm_pass():
    view = parse_llm_review_text("PASS\nlooks good")
    assert view.passed is True
    assert not view.findings


@pytest.mark.unit
def test_llm_fail():
    view = parse_llm_review_text("FAIL\nmissing tests")
    assert view.passed is False
    assert view.findings[0].rule_id == "RK-LLM"


@pytest.mark.unit
def test_findings_list():
    view = to_dev_review_view(
        [{"severity": "warning", "rule_id": "RK-ERROR", "message": "broad except"}],
        source="test",
    )
    assert view.passed is True
    assert len(view.findings) == 1


@pytest.mark.unit
def test_none_empty():
    view = to_dev_review_view(None, source="test")
    assert view.passed is True
    assert view.metadata.get("acl_empty") is True


@pytest.mark.unit
def test_adapt_never_raises():
    with patch(
        "butler.core.review_context_adapter._coerce_finding",
        side_effect=RuntimeError("boom"),
    ):
        view = to_dev_review_view({"findings": [{"x": 1}]}, source="test")
    assert view.metadata.get("acl_degraded") is True


@pytest.mark.unit
def test_merge_views():
    a = DevReviewView(
        findings=[ReviewFinding(severity="warning", rule_id="RK-SIZE", message="a")]
    )
    b = DevReviewView(
        findings=[ReviewFinding(severity="error", rule_id="RK-SECURITY", message="b")]
    )
    merged = merge_review_views(a, b)
    assert merged.passed is False
    assert len(merged.findings) == 2


@pytest.mark.unit
def test_max_severity():
    assert max_severity(
        [
            ReviewFinding(severity="info", rule_id="x", message=""),
            ReviewFinding(severity="error", rule_id="y", message=""),
        ]
    ) == "error"


@pytest.mark.unit
def test_apply_diagnostics():
    diag: dict = {}
    apply_dev_review_view_to_diagnostics(
        DevReviewView(
            passed=False,
            findings=[ReviewFinding(severity="error", rule_id="RK-TEST", message="m")],
        ),
        diag,
    )
    assert diag["dev_review_passed"] is False
    assert diag["dev_review_findings_count"] == 1


@pytest.mark.unit
def test_review_text_passed_helpers():
    assert review_text_passed("PASS ok") is True
    assert review_text_passed("FAIL bad") is False
