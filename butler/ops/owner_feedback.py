"""Owner-initiated hard feedback for G1-04 OT2 (non-delegate auto triggers)."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

OWNER_EXPLICIT_TRIGGERS = frozenset({
    "owner_hard_feedback",
    "owner_reject_delegate",
})

_MIN_TEXT_LEN = 2
_MAX_TEXT_LEN = 2000


def is_owner_explicit_trigger(trigger: str) -> bool:
    t = str(trigger or "").strip()
    return t in OWNER_EXPLICIT_TRIGGERS or t.startswith("owner_")


def record_owner_hard_feedback(
    text: str,
    *,
    session_key: str = "",
    platform: str = "wechat",
    external_id: str = "",
    kind: str = "correction",
) -> dict[str, Any]:
    """
    Append eval_feedback row with ``owner_hard_feedback`` trigger.

    Distinct from automatic ``prod_delegate_*`` production evidence.
    """
    body = str(text or "").strip()
    if len(body) < _MIN_TEXT_LEN:
        raise ValueError("反馈内容太短，请说明哪里不对或希望怎样改")

    trigger = "owner_reject_delegate" if kind == "reject" else "owner_hard_feedback"
    preview = body[:240]
    record: dict[str, Any] = {
        "ts": time.time(),
        "trigger": trigger,
        "action": "record_owner_feedback",
        "evidence": "production",
        "source": "owner_explicit",
        "platform": str(platform or "").strip() or "wechat",
        "session_key": str(session_key or "").strip(),
        "external_id": str(external_id or "").strip(),
        "feedback_text": body[:_MAX_TEXT_LEN],
        "preview": preview,
    }
    from butler.ops.eval_actions import append_eval_feedback

    append_eval_feedback(record)
    logger.info("owner hard feedback recorded trigger=%s len=%d", trigger, len(body))
    return record


def format_owner_feedback_ack(record: dict[str, Any]) -> str:
    trigger = str(record.get("trigger") or "owner_hard_feedback")
    label = "验收驳回" if trigger == "owner_reject_delegate" else "反馈"
    return (
        f"已记录{label}（计入 OT2 Owner 硬反馈）\n"
        f"触发：{trigger}\n"
        "可在 /诊断 查看 OT2 观测进度。"
    )


__all__ = [
    "format_owner_feedback_ack",
    "is_owner_explicit_trigger",
    "record_owner_hard_feedback",
]
