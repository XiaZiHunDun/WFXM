"""H4: detect owner corrections and persist via butler_remember."""

from __future__ import annotations

import re
from typing import Any

_CORRECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"刚才.{0,8}(?:不对|错了|有误|不准确)"),
    re.compile(r"你刚才.{0,8}(?:不对|错了|有误)"),
    re.compile(r"那句.{0,6}(?:不对|错了)"),
    re.compile(r"^纠正一下"),
    re.compile(r"刚才的回答.{0,6}(?:不对|错了)"),
)


def is_correction_intent(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text or text.startswith("/"):
        return False
    return any(pat.search(text) for pat in _CORRECTION_PATTERNS)


def extract_correction_content(user_text: str) -> str:
    text = (user_text or "").strip()
    for sep in ("：", ":", "，", ","):
        if sep in text:
            tail = text.split(sep, 1)[1].strip()
            if len(tail) >= 2:
                return tail
    return text


def try_handle_correction_intent(
    orchestrator: Any,
    user_text: str,
    *,
    session_key: str = "",
) -> str | None:
    """Persist correction to owner_experience when intent matches."""
    if not is_correction_intent(user_text):
        return None
    body = extract_correction_content(user_text)
    content = f"[纠正] {body}"
    from butler.core.correction_intent_ops import persist_correction_remember_safe

    result, err = persist_correction_remember_safe(
        orchestrator,
        content,
        session_key=session_key,
    )
    if err is not None:
        return err

    preview = body if len(body) <= 120 else body[:117] + "…"
    lines = [
        "已记录纠正到经验库（category=correction）：",
        f"「{preview}」",
        "",
        f"系统: {str(result)[:200]}",
        "",
        "后续可查看：记忆来源、信任（输入斜杠命令）。",
    ]
    return "\n".join(lines)


__all__ = [
    "extract_correction_content",
    "is_correction_intent",
    "try_handle_correction_intent",
]
