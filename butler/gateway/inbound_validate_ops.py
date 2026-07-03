"""Inbound message sequence validation best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def validate_openai_sequence_safe(messages: list[dict]) -> list[str] | None:
    def _run() -> list[str]:
        from butler.core.message_ir import validate_openai_sequence

        return validate_openai_sequence(messages)

    result = safe_best_effort(
        _run,
        label="inbound_validate.openai_sequence",
        default=None,
    )
    return result if isinstance(result, list) else None
