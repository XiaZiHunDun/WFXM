"""Bridge inbound steer/queue with mid-turn compaction (Codex input_queue subset)."""

from __future__ import annotations

from typing import Any

from butler.env_parse import env_truthy


def compaction_inbound_bridge_enabled() -> bool:
    return bool(env_truthy("BUTLER_COMPACTION_INBOUND_BRIDGE", default=True))


def apply_compaction_turn_followup(
    messages: list[dict[str, Any]],
    session_key: str,
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    After an explicit compaction iteration, inject urgent queue + pending steer
    so the model sees course corrections before the next sampling call.
    """
    if not compaction_inbound_bridge_enabled():
        return messages
    sk = str(session_key or "").strip() or "default"
    out = list(messages)
    injected = 0

    from butler.core.compaction_steer_bridge_ops import (
        pop_compaction_steer_text_safe,
        pop_compaction_urgent_inbound_text_safe,
    )

    urgent_text = pop_compaction_urgent_inbound_text_safe(sk)
    if urgent_text:
        out.append({
            "role": "user",
            "content": (
                "[入站紧急 — 压缩后继续]\n"
                f"{urgent_text}"
            ),
        })
        injected += 1

    steer_text = pop_compaction_steer_text_safe(sk)
    if steer_text:
        out.append({
            "role": "user",
            "content": (
                "[用户指引 — 压缩后继续，请在下轮工具结果中落实]\n"
                f"{steer_text}"
            ),
        })
        injected += 1

    if injected and isinstance(diagnostics, dict):
        diagnostics["compaction_followup_injected"] = injected
        phase = str(diagnostics.get("compaction_phase") or "")
        if phase == "mid_turn":
            diagnostics["compaction_mid_turn_steer_ok"] = True
    return out


__all__ = [
    "apply_compaction_turn_followup",
    "compaction_inbound_bridge_enabled",
]
