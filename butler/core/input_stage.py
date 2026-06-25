"""Explicit per-turn input stage (prefetch → inject) before the LLM call."""

from __future__ import annotations

from typing import Any

from butler.env_parse import env_truthy


def input_stage_enabled() -> bool:
    return env_truthy("BUTLER_INPUT_STAGE", default=True)


def begin_input_stage(diagnostics: dict[str, Any] | None) -> None:
    """Mark diagnostics that the input stage (memory prefetch) is active."""
    if diagnostics is None or not input_stage_enabled():
        return
    diagnostics["input_stage"] = "prefetch"


def normalize_inbound_text(text: str) -> str:
    """Lightweight text normalize before memory prefetch / loop (P2 multimodal stub)."""
    body = str(text or "")
    if not body:
        return body
    # Collapse unusual whitespace; strip zero-width chars often used in injection.
    body = body.replace("\u200b", "").replace("\ufeff", "")
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    return body.strip()


__all__ = [
    "begin_input_stage",
    "input_stage_enabled",
    "normalize_inbound_text",
]
