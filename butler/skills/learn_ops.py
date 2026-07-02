"""Best-effort / user-facing helpers for skill learn (P0-A)."""

from __future__ import annotations

from typing import Any


def fetch_learn_draft_safe(*, prompt: str) -> tuple[str | None, str | None]:
    """Return (raw_response, error_message)."""
    try:
        from butler.transport.auxiliary_client import auxiliary_complete

        raw = auxiliary_complete(
            prompt,
            task="post_session",
            system="You output strict JSON only.",
        )
        return raw, None
    except Exception as exc:
        return None, f"技能学习 LLM 调用失败: {exc}"


def create_learned_skill_safe(skill_manager: Any, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (outcome, error_message)."""
    try:
        outcome = skill_manager.create(
            payload["name"],
            payload["description"],
            payload["triggers"],
            payload["content"],
        )
        return str(outcome), None
    except Exception as exc:
        return None, f"技能学习失败: {exc}"
