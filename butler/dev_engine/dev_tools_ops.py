"""Dev tools best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, cast

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def coding_knowledge_verify_safe(
    state: Any,
    *,
    test_passed: bool,
    test_detail: str,
) -> list[str]:
    activated = getattr(state, "_coding_knowledge_theorems", None)
    if not activated or not state.edit_history:
        return []

    def _run() -> list[str]:
        from butler.dev_engine.coding_knowledge import dual_verify as ck_dual_verify

        last_edit = state.edit_history[-1]
        code = last_edit.new_content or last_edit.patch_new or ""
        if not code:
            return []
        ck_result = ck_dual_verify(
            code,
            activated,
            test_passed=test_passed,
            test_detail=test_detail,
        )
        violations = ck_result.violated_theorems
        state.coding_knowledge.violated_theorems = violations
        return list(violations)

    result = safe_best_effort(_run, label="dev_tools.coding_knowledge_verify", default=[])
    return list(result or [])


def auto_review_after_verify_safe(
    workspace: str,
    *,
    session_key: str,
) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        from butler.dev_engine.dev_tools import auto_review_enabled, tool_dev_review

        if not auto_review_enabled():
            return {}
        return cast(dict[str, Any], tool_dev_review(str(workspace), session_key=session_key, from_auto_verify=True))

    return cast(dict[str, Any] | None, safe_best_effort(_run, label="dev_tools.auto_review", default=None))


def apply_dev_review_diagnostics_safe(view: Any, diagnostics: dict[str, Any]) -> None:
    def _run() -> None:
        from butler.core.review_context_adapter import apply_dev_review_view_to_diagnostics

        apply_dev_review_view_to_diagnostics(view, diagnostics)

    safe_best_effort(_run, label="dev_tools.review_diagnostics", default=None)


def review_closure_hooks_safe(
    view: Any,
    *,
    session_key: str,
    task_preview: str,
) -> None:
    def _run() -> None:
        from butler.execution_context import get_current_session_key
        from butler.dev_engine.review_closure import (
            maybe_persist_review_closure,
            maybe_queue_experience_candidate,
        )

        sk = str(get_current_session_key() or session_key or "")
        maybe_persist_review_closure(view, session_key=sk, source="dev_review")
        maybe_queue_experience_candidate(view, task_preview=task_preview)

    safe_best_effort(_run, label="dev_tools.review_closure", default=None)


def pytest_run_failed_payload(exc: BaseException) -> dict[str, Any]:
    return {"error": str(exc), "code": "PYTEST_RUN_FAILED"}


def pytest_timeout_payload(path: str) -> dict[str, Any]:
    return {
        "passed": False,
        "exit_code": -1,
        "path": path,
        "error": "pytest timeout",
        "hint": "Tests took too long; fix implementation or reduce scope.",
    }


def run_pytest_command_loud(
    *,
    ws: Any,
    test_arg: str,
    rel: str,
    timeout: int,
) -> Any:
    """Return CompletedProcess on success, or dict error payload."""
    import subprocess

    try:
        return subprocess.run(
            ["python3", "-m", "pytest", test_arg, "-q", "--tb=short"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=max(5, min(int(timeout), 120)),
        )
    except subprocess.TimeoutExpired:
        return pytest_timeout_payload(rel)
    except Exception as exc:
        return pytest_run_failed_payload(exc)


def build_b9_verify_hint_safe(failure_tail: str) -> str:
    def _run() -> str:
        from butler.dev_engine.b9_live_tuning import build_b9_verify_hint

        return str(build_b9_verify_hint(failure_tail) or "")

    result = safe_best_effort(_run, label="dev_tools.b9_verify_hint", default="")
    return str(result or "")


def resolve_session_key_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_audit_session_key

        return str(get_audit_session_key(fallback="_default") or "_default")

    result = safe_best_effort(_run, label="dev_tools.session_key", default="_default")
    return str(result or "_default")
