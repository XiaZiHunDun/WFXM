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
)

LINGWEN1_CAPTURE_NOTE = (
    "LingWen1 audit seeded as lingwen1-demo-add-fix; live capture via BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES."
)

PROMOTED_TASK_IDS: frozenset[str] = frozenset(b.task_id for b in BINDINGS)


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


__all__ = [
    "BINDINGS",
    "LINGWEN1_CAPTURE_NOTE",
    "PROMOTED_TASK_IDS",
    "ProdPromotedBinding",
    "binding_for_task",
    "promoted_probe_task_ids",
    "resolve_production_failure_to_task",
]
