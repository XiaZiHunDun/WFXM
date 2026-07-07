"""Fusion client best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def record_fusion_llm_cost_safe(session_key: str, usage: Any) -> None:
    if not session_key or usage is None:
        return

    def _run() -> None:
        from butler.ops.cost_tracker import get_session_cost

        get_session_cost(session_key).record_llm_call(
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

    safe_best_effort(_run, label="fusion_client.record_cost", default=None)


def current_fusion_session_key_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "")

    result = safe_best_effort(
        _run,
        label="fusion_client.session_key",
        default="",
    )
    return str(result or "")


def fusion_complete_or_raise_unavailable(complete_fn: Any, prompt: str) -> str:
    from butler.skills.consolidator import ConsolidatorLLMUnavailable

    try:
        return str(complete_fn(prompt))
    except ConsolidatorLLMUnavailable:
        raise
    except Exception as exc:
        raise ConsolidatorLLMUnavailable(str(exc)) from exc
