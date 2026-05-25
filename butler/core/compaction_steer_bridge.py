"""Bridge inbound steer/queue with mid-turn compaction (Codex input_queue subset)."""

from __future__ import annotations

import logging
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def compaction_inbound_bridge_enabled() -> bool:
    return env_truthy("BUTLER_COMPACTION_INBOUND_BRIDGE", default=True)


def apply_compaction_turn_followup(
    messages: list[dict],
    session_key: str,
    diagnostics: dict[str, Any] | None = None,
) -> list[dict]:
    """
    After an explicit compaction iteration, inject urgent queue + pending steer
    so the model sees course corrections before the next sampling call.
    """
    if not compaction_inbound_bridge_enabled():
        return messages
    sk = str(session_key or "").strip() or "default"
    out = list(messages)
    injected = 0

    try:
        from butler.gateway.message_queue import pop_urgent_inbound

        item = pop_urgent_inbound(sk)
        if item is not None and item.text.strip():
            out.append({
                "role": "user",
                "content": (
                    "[入站紧急 — 压缩后继续]\n"
                    f"{item.text.strip()}"
                ),
            })
            injected += 1
    except Exception as exc:
        logger.debug("compaction urgent inbound: %s", exc)

    try:
        from butler.core.steer import drain_steer, pending_steer

        steer_text = pending_steer(sk)
        if steer_text and steer_text.strip():
            out.append({
                "role": "user",
                "content": (
                    "[用户指引 — 压缩后继续，请在下轮工具结果中落实]\n"
                    f"{steer_text.strip()}"
                ),
            })
            drain_steer(sk)
            injected += 1
    except Exception as exc:
        logger.debug("compaction steer inject: %s", exc)

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
