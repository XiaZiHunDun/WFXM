"""Best-effort helpers for tool guardrails (P0-A)."""

from __future__ import annotations

from typing import Any, Mapping

from butler.core.best_effort import safe_best_effort


def mutation_classification_hint(tool_name: str, result: str) -> tuple[bool, str] | None:
    """Return (failed, suffix) from mutation classification, or None to continue."""

    def _run() -> tuple[bool, str] | None:
        from butler.core.tool_result_classification import (
            file_mutation_result_landed,
            is_file_mutating_tool,
            mutation_result_not_landed,
        )
        from butler.tool_guardrails import _safe_json_loads

        if file_mutation_result_landed(tool_name, result):
            return False, ""
        if mutation_result_not_landed(tool_name, result):
            return True, " [mutation_not_landed]"
        if is_file_mutating_tool(tool_name):
            data = _safe_json_loads(result or "")
            if isinstance(data, dict) and data.get("error"):
                return True, " [error]"
        return None

    hint = safe_best_effort(
        _run,
        label="tool_guardrails.mutation_classify",
        default=None,
    )
    return hint if isinstance(hint, tuple) else None


def reset_tool_loop_detector_safe() -> None:
    def _run() -> None:
        from butler.core.tool_loop_detect import get_tool_loop_detector

        get_tool_loop_detector().reset_for_turn()

    safe_best_effort(_run, label="tool_guardrails.loop_reset", default=None)


def check_tool_loop_before_call_safe(
    tool_name: str,
    args: Mapping[str, Any] | None,
) -> Any | None:
    def _run() -> Any:
        from butler.core.tool_loop_detect import get_tool_loop_detector

        return get_tool_loop_detector().check_before_call(tool_name, args)

    return safe_best_effort(
        _run,
        label="tool_guardrails.loop_before",
        default=None,
    )


def record_tool_loop_after_call_safe(
    tool_name: str,
    args_hash: str,
    result: str,
) -> None:
    def _run() -> None:
        from butler.core.tool_loop_detect import get_tool_loop_detector

        get_tool_loop_detector().record_call(tool_name, args_hash, result)

    safe_best_effort(_run, label="tool_guardrails.loop_after", default=None)
