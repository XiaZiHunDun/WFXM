"""Anti-corruption adapter: external review shapes → DevReviewView."""

from __future__ import annotations

from typing import Any

from butler.contracts.review_ports import DevReviewView, ReviewFinding
from butler.core.review_context_adapter_ops import (
    _coerce_finding,
    max_severity,
    parse_llm_review_text,
    review_text_passed,
)


def to_dev_review_view(
    incoming: Any,
    *,
    source: str = "unknown",
) -> DevReviewView:
    """Convert external review payload; never raises."""
    from butler.core.review_context_adapter_ops import to_dev_review_view_loud

    return to_dev_review_view_loud(incoming, source=source)


def apply_dev_review_view_to_diagnostics(
    view: DevReviewView,
    diagnostics: dict[str, Any] | None,
) -> None:
    if not isinstance(diagnostics, dict):
        return
    diagnostics["dev_review_passed"] = view.passed
    diagnostics["dev_review_findings_count"] = len(view.findings)
    diagnostics["dev_review_severity_max"] = max_severity(view.findings)
    if view.suggestions:
        diagnostics["dev_review_suggestions_count"] = len(view.suggestions)
    shape = view.metadata.get("acl_shape")
    if shape:
        diagnostics["dev_review_acl_shape"] = shape


def apply_dev_review_view_to_state(view: DevReviewView, state: Any) -> None:
    """Attach review summary on DevState (best-effort)."""
    from butler.core.review_context_adapter_ops import apply_dev_review_view_to_state_safe

    apply_dev_review_view_to_state_safe(view, state)


def merge_review_views(*views: DevReviewView) -> DevReviewView:
    findings: list[ReviewFinding] = []
    suggestions: list[str] = []
    meta: dict[str, Any] = {"source": "merged"}
    for view in views:
        findings.extend(view.findings)
        suggestions.extend(view.suggestions)
    passed = not any(f.severity == "error" for f in findings)
    return DevReviewView(
        passed=passed,
        findings=findings,
        suggestions=suggestions[:12],
        metadata=meta,
    )


__all__ = [
    "apply_dev_review_view_to_diagnostics",
    "apply_dev_review_view_to_state",
    "merge_review_views",
    "parse_llm_review_text",
    "review_text_passed",
    "to_dev_review_view",
]
