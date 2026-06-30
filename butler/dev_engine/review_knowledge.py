"""Review Knowledge Layer — rubric registry for deterministic code review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from butler.contracts.review_ports import ReviewFinding


@dataclass(frozen=True)
class ReviewRule:
    rule_id: str
    title: str
    element: str
    description: str


REVIEW_RULES: dict[str, ReviewRule] = {
    "RK-BOUNDARY": ReviewRule(
        rule_id="RK-BOUNDARY",
        title="Layer boundary import",
        element="BoundaryInterface",
        description="core/ must not import gateway directly",
    ),
    "RK-ERROR": ReviewRule(
        rule_id="RK-ERROR",
        title="Broad exception swallow",
        element="ErrorHandling",
        description="except Exception without log or re-raise",
    ),
    "RK-SIZE": ReviewRule(
        rule_id="RK-SIZE",
        title="Function/file size budget",
        element="Composition",
        description="Functions or files exceed configured line budget",
    ),
    "RK-TEST": ReviewRule(
        rule_id="RK-TEST",
        title="Test touch heuristic",
        element="TypeSchema",
        description="Changed .py without tests/ mention",
    ),
    "RK-SECURITY": ReviewRule(
        rule_id="RK-SECURITY",
        title="Hardcoded secret pattern",
        element="BoundaryInterface",
        description="Likely hardcoded credential in source",
    ),
    "RK-LLM": ReviewRule(
        rule_id="RK-LLM",
        title="LLM review finding",
        element="BoundaryInterface",
        description="Unstructured review_agent output",
    ),
}


RuleChecker = Callable[..., list[ReviewFinding]]


def list_rule_ids() -> list[str]:
    return list(REVIEW_RULES.keys())
