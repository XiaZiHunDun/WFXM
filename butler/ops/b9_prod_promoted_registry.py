"""Map production delegate_failures audit rows → implemented B9L_prod_* tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProdPromotedBinding:
    task_id: str
    source_task_id: str
    failure_reason: str
    pattern_summary: str
    audit_trace_id: str = ""


# Substrings matched against lowercased task_preview (+ issues blob).
_PREVIEW_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("read_file", "greet.py", "read_state"), "B9L_prod_read_state_greet"),
    (("greet.py", "hello", "hi"), "B9L_prod_demo_fix_greet_return"),
    (("main.py", "helpers"), "B9L_prod_main_helpers_import"),
    (("clamp", "logic.py"), "B9L_prod_patch_wrong"),
    (("divider", "divide"), "B9L_prod_verify_fail"),
    (("formatter", "label"), "B9L_prod_no_test"),
    (("getdata", "get_data", "pkg/client"), "B9L_prod_cross_module_rename"),
    (("rename", "getdata", "client.py"), "B9L_prod_cross_module_rename"),
    (("lingwen1", "demo/hello", "add"), "B9L_prod_lingwen_demo_add"),
    (("demo/hello.py", "add(a, b)"), "B9L_prod_lingwen_demo_add"),
    (("workflow_guard", "待修复"), "B9L_prod_lingwen_workflow_guard"),
    (("workflow_guard", "待修复", "novel-factory"), "B9L_prod_lingwen_workflow_guard"),
    (("has_open_completed", "completed", "待修复"), "B9L_prod_lingwen_workflow_guard"),
    (("constants.py", "docstring", "max_retries"), "B9L_prod_lingwen_constants_docstring"),
    (("constants.py", "module docstring"), "B9L_prod_lingwen_constants_docstring"),
    (("validate_progress", "进度验证"), "B9L_prod_lingwen_validate_progress"),
    (("novel-factory/scripts/validate_progress", "进度验证"), "B9L_prod_lingwen_validate_progress"),
)

BINDINGS: tuple[ProdPromotedBinding, ...] = (
    ProdPromotedBinding(
        task_id="B9L_prod_demo_fix_greet_return",
        source_task_id="demo-fix-greet-return",
        failure_reason="verify_fail",
        pattern_summary="greet() returns hi but test expects hello — patch return literal only",
        audit_trace_id="trace-demo-greet-001",
    ),
    ProdPromotedBinding(
        task_id="B9L_prod_read_state_greet",
        source_task_id="task_3a0bc9cf7f14",
        failure_reason="verify_failed",
        pattern_summary="READ_STATE_REQUIRED: read_file greet.py before patch; then fix return literal",
        audit_trace_id="",
    ),
    ProdPromotedBinding(
        task_id="B9L_prod_main_helpers_import",
        source_task_id="task_12f8eb65e703",
        failure_reason="verify_failed",
        pattern_summary="main.py imports helper but module is helpers.py — list_directory then patch import",
        audit_trace_id="",
    ),
    ProdPromotedBinding(
        task_id="B9L_prod_cross_module_rename",
        source_task_id="task_1c1398702de8",
        failure_reason="verify_failed",
        pattern_summary="Rename getData→get_data in pkg/client.py; read_file both files before patch",
        audit_trace_id="",
    ),
    ProdPromotedBinding(
        task_id="B9L_prod_lingwen_demo_add",
        source_task_id="lingwen1-demo-add-fix",
        failure_reason="verify_fail",
        pattern_summary="LingWen1 demo/hello.py add() uses subtraction — patch to a + b",
        audit_trace_id="trace-lingwen1-demo-add-001",
    ),
    ProdPromotedBinding(
        task_id="B9L_prod_lingwen_workflow_guard",
        source_task_id="lingwen1-workflow-guard-fix",
        failure_reason="verify_fail",
        pattern_summary="workflow_guard has_open_completed ignores 待修复 — return True in open branch",
        audit_trace_id="trace-lingwen1-workflow-guard-001",
    ),
    ProdPromotedBinding(
        task_id="B9L_prod_lingwen_constants_docstring",
        source_task_id="lingwen1-sample-constants-comment",
        failure_reason="verify_fail",
        pattern_summary="LingWen1 constants.py missing module docstring — read_file then prepend docstring",
        audit_trace_id="",
    ),
    ProdPromotedBinding(
        task_id="B9L_prod_lingwen_validate_progress",
        source_task_id="lingwen1-sample-validate-progress",
        failure_reason="verify_fail",
        pattern_summary="Run novel-factory validate_progress; fix workflow_state unclosed completed batch",
        audit_trace_id="",
    ),
)

LINGWEN1_CAPTURE_NOTE = (
    "LingWen1 audit seeds: demo-add + workflow-guard; live capture via BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES."
)

PROMOTED_TASK_IDS: frozenset[str] = frozenset(b.task_id for b in BINDINGS)

# Stretch: isolated-workspace LIVE may fail while real LingWen prod sample passes.
PROMOTED_STRETCH_TASK_IDS: frozenset[str] = frozenset(
    {"B9L_prod_lingwen_validate_progress"},
)

PROMOTED_CORE_TASK_IDS: frozenset[str] = PROMOTED_TASK_IDS - PROMOTED_STRETCH_TASK_IDS


def _blob(record: dict[str, Any]) -> str:
    preview = str(record.get("task_preview") or record.get("task") or "")
    issues = " ".join(str(i) for i in (record.get("issues") or [])[:5])
    return f"{preview} {issues}".lower()


def resolve_production_failure_to_task(record: dict[str, Any]) -> str | None:
    """Return implemented B9L_prod_* task_id if audit row matches a promoted pattern."""
    text = _blob(record)
    if "read_state" in text or "必须先调用 read_file" in text:
        if "greet" in text and "hello" in text:
            return "B9L_prod_read_state_greet"
    for needles, task_id in _PREVIEW_RULES:
        if all(n in text for n in needles):
            return task_id
    return None


def binding_for_task(task_id: str) -> ProdPromotedBinding | None:
    for b in BINDINGS:
        if b.task_id == task_id:
            return b
    return None


def promoted_probe_task_ids() -> list[str]:
    return sorted(PROMOTED_TASK_IDS)


def promoted_core_task_ids() -> list[str]:
    return sorted(PROMOTED_CORE_TASK_IDS)


def promoted_stretch_task_ids() -> list[str]:
    return sorted(PROMOTED_STRETCH_TASK_IDS)


def summarize_promoted_probe_layers(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Split promoted LIVE probe into core (gate) vs stretch (non-blocking)."""
    core_ids = PROMOTED_CORE_TASK_IDS
    stretch_ids = PROMOTED_STRETCH_TASK_IDS
    core_rows = [r for r in results if str(r.get("task_id") or "") in core_ids]
    stretch_rows = [r for r in results if str(r.get("task_id") or "") in stretch_ids]
    core_passed = sum(1 for r in core_rows if r.get("passed"))
    stretch_passed = sum(1 for r in stretch_rows if r.get("passed"))
    return {
        "core": {
            "passed": core_passed,
            "total": len(core_rows),
            "pass_rate": round(core_passed / len(core_rows), 4) if core_rows else 0.0,
            "task_ids": promoted_core_task_ids(),
            "failed_task_ids": [
                str(r.get("task_id")) for r in core_rows if not r.get("passed")
            ],
        },
        "stretch": {
            "passed": stretch_passed,
            "total": len(stretch_rows),
            "pass_rate": round(stretch_passed / len(stretch_rows), 4) if stretch_rows else 0.0,
            "task_ids": promoted_stretch_task_ids(),
            "failed_task_ids": [
                str(r.get("task_id")) for r in stretch_rows if not r.get("passed")
            ],
        },
    }


__all__ = [
    "BINDINGS",
    "LINGWEN1_CAPTURE_NOTE",
    "PROMOTED_CORE_TASK_IDS",
    "PROMOTED_STRETCH_TASK_IDS",
    "PROMOTED_TASK_IDS",
    "ProdPromotedBinding",
    "binding_for_task",
    "promoted_core_task_ids",
    "promoted_probe_task_ids",
    "promoted_stretch_task_ids",
    "resolve_production_failure_to_task",
    "summarize_promoted_probe_layers",
]
