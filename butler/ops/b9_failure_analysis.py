"""Classify B9 LIVE failures for tuning (no patch vs wrong patch vs verify gap)."""

from __future__ import annotations

from typing import Any


def classify_b9_failure(
    *,
    task_id: str,
    passed: bool,
    tools_used: list[str] | None,
    failure_reasons: list[str] | None,
) -> str:
    if passed:
        return "passed"
    tools = {str(t).strip().lower() for t in (tools_used or []) if t}
    reasons = " ".join(failure_reasons or []).lower()
    has_patch = "patch" in tools or "write_file" in tools
    has_terminal = "terminal" in tools
    if not has_patch:
        return "no_edit"
    if has_patch and has_terminal and ("failed" in reasons or "error" in reasons):
        return "wrong_patch"
    if has_patch and not has_terminal:
        return "patch_no_verify"
    if "modulenotfounderror" in reasons or "importerror" in reasons:
        return "import_fix_incomplete"
    if "assert" in reasons:
        return "logic_fix_incomplete"
    return "other_fail"


def analyze_b9_live_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a B9 LIVE result list (from report.to_dict or audit JSON)."""
    rows: list[dict[str, Any]] = []
    by_class: dict[str, int] = {}
    for r in results:
        cls = classify_b9_failure(
            task_id=str(r.get("task_id") or ""),
            passed=bool(r.get("passed")),
            tools_used=list(r.get("tools_used") or []),
            failure_reasons=list(r.get("failure_reasons") or []),
        )
        by_class[cls] = by_class.get(cls, 0) + 1
        rows.append({
            "task_id": r.get("task_id"),
            "passed": r.get("passed"),
            "classification": cls,
            "tools_used": r.get("tools_used") or [],
            "failure_snippet": (r.get("failure_reasons") or [""])[0][:200],
        })
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("passed")),
        "by_classification": by_class,
        "tasks": rows,
    }


def analyze_probe_tasks(results: list[dict[str, Any]]) -> dict[str, Any]:
    from butler.dev_engine.b9_live_tuning import B9_TUNING_PROBE_TASK_IDS

    wanted = set(B9_TUNING_PROBE_TASK_IDS)
    subset = [r for r in results if r.get("task_id") in wanted]
    return analyze_b9_live_results(subset)


__all__ = [
    "analyze_b9_live_results",
    "analyze_probe_tasks",
    "classify_b9_failure",
]
