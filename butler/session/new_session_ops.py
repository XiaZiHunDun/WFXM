"""New-session boundary best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def purge_conversation_experience_safe(
    orchestrator: Any,
    tag: str,
) -> tuple[int, str]:
    """Return (removed_count, error_message)."""

    def _run() -> int:
        bm = getattr(orchestrator, "butler_memory", None)
        if bm is not None and hasattr(bm, "delete_conversation_for_session"):
            purge = bm.delete_conversation_for_session(tag)
            return int(purge.get("removed_rows") or 0)
        exp = getattr(bm, "experience", None) if bm is not None else None
        if exp is not None and hasattr(exp, "delete_conversation_for_session"):
            removed, _ids = exp.delete_conversation_for_session(tag)
            return int(removed)
        return 0

    result = safe_best_effort(_run, label="new_session.purge_conversation", default=None)
    if result is None:
        return 0, "purge_failed"
    return int(result), ""


def clear_provider_turn_buffer_safe(orchestrator: Any) -> None:
    def _run() -> None:
        provider = getattr(orchestrator, "memory_provider", None) or getattr(
            orchestrator, "_memory_provider", None
        )
        if provider is not None and hasattr(provider, "clear_turn_buffer"):
            provider.clear_turn_buffer()

    safe_best_effort(_run, label="new_session.clear_turn_buffer", default=None)


def reset_inbound_idempotency_safe(session_id: str) -> None:
    def _run() -> None:
        from butler.contracts.inbound_idempotency_registry import get_inbound_idempotency_port

        port = get_inbound_idempotency_port()
        if port is not None:
            port.reset_session(session_id)

    safe_best_effort(_run, label="new_session.inbound_idempotency", default=None)


def clear_retrieval_telemetry_safe(session_id: str) -> None:
    def _run() -> None:
        from butler.memory.retrieval_telemetry import clear_last_retrieval

        clear_last_retrieval(session_id)

    safe_best_effort(_run, label="new_session.retrieval_telemetry", default=None)


def reset_tool_result_state_safe(session_id: str) -> None:
    def _run() -> None:
        from butler.core.tool_result_storage import (
            reset_inject_once_state,
            reset_replacement_state,
        )

        reset_inject_once_state(session_id)
        reset_replacement_state(session_id)

    safe_best_effort(_run, label="new_session.tool_result_state", default=None)


def run_session_start_hooks_safe() -> None:
    def _run() -> None:
        from butler.hooks.runner import run_session_start_hooks

        run_session_start_hooks(source="clear")

    safe_best_effort(_run, label="new_session.session_start_hooks", default=None)
