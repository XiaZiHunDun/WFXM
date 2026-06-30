"""Anti-corruption adapter: external review shapes → DevReviewView."""

from __future__ import annotations

import logging
import re
from typing import Any

from butler.contracts.review_ports import DevReviewView, ReviewFinding
from butler.core.best_effort import record_best_effort_skip
from butler.core.plan_snapshot import qa_response_is_fail

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"error": 3, "warning": 2, "info": 1}


def _coerce_finding(item: Any) -> ReviewFinding | None:
    if isinstance(item, ReviewFinding):
        return item
    if not isinstance(item, dict):
        return None
    sev = str(item.get("severity") or "warning").strip().lower()
    if sev not in ("error", "warning", "info"):
        sev = "warning"
    return ReviewFinding(
        severity=sev,  # type: ignore[arg-type]
        rule_id=str(item.get("rule_id") or item.get("rule") or "")[:64],
        file=str(item.get("file") or "")[:260],
        line=int(item.get("line") or 0),
        message=str(item.get("message") or "")[:500],
        evidence=str(item.get("evidence") or "")[:400],
    )


def _findings_from_any(items: Any) -> list[ReviewFinding]:
    if not isinstance(items, list):
        return []
    out: list[ReviewFinding] = []
    for item in items:
        finding = _coerce_finding(item)
        if finding is not None:
            out.append(finding)
    return out


def parse_llm_review_text(text: str, *, source: str = "llm_review") -> DevReviewView:
    """Parse review_agent PASS/FAIL headline + body into DevReviewView."""
    raw = str(text or "").strip()
    if not raw:
        return DevReviewView(
            passed=True,
            metadata={"source": source, "acl_shape": "empty"},
        )
    lines = raw.splitlines()
    head = lines[0].strip().upper() if lines else ""
    passed = head.startswith("PASS")
    failed = qa_response_is_fail(raw)
    if failed:
        passed = False
    elif head.startswith("PASS"):
        passed = True
    findings: list[ReviewFinding] = []
    if not passed:
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw
        findings.append(
            ReviewFinding(
                severity="error",
                rule_id="RK-LLM",
                message=body[:500] or "LLM review FAIL",
                evidence=head[:120],
            )
        )
    return DevReviewView(
        passed=passed,
        findings=findings,
        metadata={"source": source, "acl_shape": "llm_text", "headline": head[:32]},
    )


def to_dev_review_view(
    incoming: Any,
    *,
    source: str = "unknown",
) -> DevReviewView:
    """Convert external review payload; never raises."""
    try:
        if incoming is None:
            return DevReviewView(
                passed=True,
                metadata={"source": source, "acl_shape": "none", "acl_empty": True},
            )
        if isinstance(incoming, DevReviewView):
            return incoming
        if isinstance(incoming, str):
            return parse_llm_review_text(incoming, source=source)
        if isinstance(incoming, dict):
            findings = _findings_from_any(incoming.get("findings"))
            suggestions = [
                str(s)[:280] for s in (incoming.get("suggestions") or []) if str(s).strip()
            ]
            passed = incoming.get("passed")
            if passed is None:
                passed = not any(f.severity == "error" for f in findings)
            return DevReviewView(
                passed=bool(passed),
                findings=findings,
                suggestions=suggestions[:12],
                metadata={"source": source, "acl_shape": "dict"},
            )
        if isinstance(incoming, list):
            findings = _findings_from_any(incoming)
            return DevReviewView(
                passed=not any(f.severity == "error" for f in findings),
                findings=findings,
                metadata={"source": source, "acl_shape": "findings_list"},
            )
        return DevReviewView(
            passed=True,
            metadata={"source": source, "acl_shape": "fallback", "acl_warn": "unknown_shape"},
        )
    except Exception as exc:
        logger.debug("review ACL adapt failed (%s): %s", source, exc)
        record_best_effort_skip(f"review_acl.{source}", exc)
        return DevReviewView(
            passed=True,
            metadata={
                "source": source,
                "acl_degraded": True,
                "acl_error": str(exc)[:160],
            },
        )


def max_severity(findings: list[ReviewFinding]) -> str:
    best = "info"
    for f in findings:
        if _SEVERITY_ORDER.get(f.severity, 0) > _SEVERITY_ORDER.get(best, 0):
            best = f.severity
    return best


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
    try:
        from butler.dev_engine.dev_state import ReviewSummary

        state.review_summary = ReviewSummary(
            passed=view.passed,
            findings_count=len(view.findings),
            severity_max=max_severity(view.findings),
            findings=[f.model_dump() for f in view.findings[:24]],
            suggestions=list(view.suggestions[:12]),
        )
    except Exception as exc:
        logger.debug("apply review view to state skipped: %s", exc)


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


_HEADLINE_PASS_RE = re.compile(r"^\s*PASS\b", re.I)


def review_text_passed(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return True
    if qa_response_is_fail(raw):
        return False
    first = raw.splitlines()[0].strip()
    return bool(_HEADLINE_PASS_RE.match(first))
