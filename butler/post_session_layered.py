"""Layered persona/preference/experience extraction for session_summary.json."""

from __future__ import annotations

import json
import logging
from typing import Any

from butler.env_parse import env_truthy
from butler.post_session import _format_messages, _parse_json_from_response

logger = logging.getLogger(__name__)

_LAYERED_PROMPT = """从以下对话提取用户画像分层摘要。只输出 JSON，不要 markdown。

{{
  "persona": ["称呼/角色/沟通风格，最多3条"],
  "preference": ["偏好与习惯，最多3条"],
  "experience": ["可复用的经验教训，最多3条"]
}}

无内容则对应字段为空数组。不要编造对话中未出现的信息。

## 对话
{transcript}
"""


def post_session_layered_enabled() -> bool:
    return env_truthy("BUTLER_POST_SESSION_LAYERED", default=False)


async def extract_layered_summary(
    messages: list[dict],
    llm_call: Any,
) -> dict[str, list[str]]:
    """Return persona/preference/experience string lists."""
    empty: dict[str, list[str]] = {"persona": [], "preference": [], "experience": []}
    if not post_session_layered_enabled() or not llm_call:
        return empty
    transcript = _format_messages(messages, max_chars=8000)
    if len(transcript) < 200:
        return empty
    prompt = _LAYERED_PROMPT.format(transcript=transcript)
    try:
        import inspect

        raw = llm_call(prompt)
        if inspect.isawaitable(raw):
            raw = await raw
        data = _parse_json_from_response(str(raw or ""))
    except Exception as exc:
        logger.debug("Layered post-session extract failed: %s", exc)
        return empty
    if not isinstance(data, dict):
        return empty
    out: dict[str, list[str]] = {}
    for key in ("persona", "preference", "experience"):
        val = data.get(key) or []
        if isinstance(val, list):
            out[key] = [str(x).strip()[:240] for x in val if str(x).strip()][:3]
        else:
            out[key] = []
    return out


__all__ = ["extract_layered_summary", "post_session_layered_enabled"]
