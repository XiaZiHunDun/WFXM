"""Session cost calibration best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_llm_cost_event_safe(
    *,
    input_tokens: int,
    output_tokens: int,
    model: str,
    session_key: str,
) -> None:
    def _run() -> None:
        from butler.ops.cost_calibration import record_llm_cost_event

        record_llm_cost_event(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            session_key=session_key,
        )

    safe_best_effort(_run, label="cost_tracker.llm_cost_event", default=None)


def record_tool_cost_event_safe(
    *,
    tool_name: str,
    bucket: str,
    session_key: str,
) -> None:
    def _run() -> None:
        from butler.ops.cost_calibration import record_tool_cost_event

        record_tool_cost_event(
            tool_name=tool_name,
            bucket=bucket,
            session_key=session_key,
        )

    safe_best_effort(_run, label="cost_tracker.tool_cost_event", default=None)
