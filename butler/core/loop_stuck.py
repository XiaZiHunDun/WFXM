"""Map guardrail / loop-detect halts to LoopStatus.STUCK."""

from __future__ import annotations

_STUCK_CODES = frozenset({
    "circuit",
    "ping_pong",
    "poll",
    "ping_pong_soft_nudge",
})


def guardrail_stuck_message(guardrails: object | None) -> str | None:
    if guardrails is None:
        return None
    dec = getattr(guardrails, "halt_decision", None)
    if dec is None:
        return None
    code = str(getattr(dec, "code", "") or "")
    action = str(getattr(dec, "action", "") or "")
    if action != "block" and code not in ("circuit", "ping_pong"):
        if code != "poll":
            return None
    if code not in _STUCK_CODES and not code.startswith("ping_pong"):
        if code != "circuit":
            return None
    msg = str(getattr(dec, "message", "") or "").strip()
    return msg or "工具循环检测：本轮无法继续自动执行。"


def loop_detect_stuck_message(guardrails: object | None) -> str | None:
    """Alias for guardrail halt after tool_loop_detect critical paths."""
    return guardrail_stuck_message(guardrails)


__all__ = ["guardrail_stuck_message", "loop_detect_stuck_message"]
