"""Controlled skill learn flow (WeChat /skills learn + CLI ``butler skills learn``)."""

from __future__ import annotations

import json
import re
from typing import Any

LEARN_PROMPT = """根据以下描述起草一条 Butler Skill（YAML frontmatter + Markdown 正文）。
只输出 JSON：{{"name": "...", "description": "...", "triggers": ["..."], "content": "..."}}
描述：{description}
"""

_MIN_DESC_LEN = 8


def _strip_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if text.lower().startswith("json"):
        text = text[4:].lstrip()
    return text.strip()


def parse_learn_response(raw: str) -> dict[str, Any]:
    """Parse auxiliary model JSON for skill learn."""
    data = json.loads(_strip_json_fence(raw))
    if not isinstance(data, dict):
        raise ValueError("invalid learn payload")
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("missing skill name")
    return {
        "name": name,
        "description": str(data.get("description") or "").strip(),
        "triggers": [str(t).strip() for t in (data.get("triggers") or []) if str(t).strip()],
        "content": str(data.get("content") or "").strip(),
    }


def run_skill_learn(description: str, skill_manager: Any) -> dict[str, Any]:
    """Draft skill via auxiliary LLM and queue/create through ``skill_manager``."""
    desc = (description or "").strip()
    if len(desc) < _MIN_DESC_LEN:
        return {
            "ok": False,
            "error": f"描述至少 {_MIN_DESC_LEN} 字。用法: butler skills learn \"<描述>\"",
        }
    try:
        from butler.transport.auxiliary_client import auxiliary_complete

        raw = auxiliary_complete(
            LEARN_PROMPT.format(description=desc),
            task="post_session",
            system="You output strict JSON only.",
        )
    except Exception as exc:
        return {"ok": False, "error": f"技能学习 LLM 调用失败: {exc}"}

    try:
        payload = parse_learn_response(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "error": f"技能学习：模型返回无效 JSON（{exc}）"}

    try:
        outcome = skill_manager.create(
            payload["name"],
            payload["description"],
            payload["triggers"],
            payload["content"],
        )
    except Exception as exc:
        return {"ok": False, "error": f"技能学习失败: {exc}"}

    name = payload["name"]
    if outcome == "pending":
        msg = (
            f"技能「{name}」已入待审队列。"
            "微信: /技能待审 · /批准技能 ；CLI: butler skills pending / approve"
        )
    else:
        msg = f"技能「{name}」已{outcome}。"
    return {"ok": True, "name": name, "outcome": outcome, "message": msg}


__all__ = ["LEARN_PROMPT", "parse_learn_response", "run_skill_learn"]
