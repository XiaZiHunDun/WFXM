"""H4: detect owner corrections and persist via butler_remember."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

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
    try:
        from butler.tools.memory_tools import tool_butler_remember
        from butler.execution_context import use_execution_context

        with use_execution_context(orchestrator, session_key=session_key):
            result = tool_butler_remember(
                scope="owner_experience",
                content=content,
                category="correction",
            )
    except Exception as exc:
        logger.warning("correction intent remember failed: %s", exc)
        return f"纠正意图已识别，但写入失败：{exc}"

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
