"""Ephemeral execution-mode banners from user magic words (OMO keyword-detector lite)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_RULES: list[dict[str, str]] = [
    {
        "keywords": "全力,ulw,ultrawork",
        "banner": (
            "[Intent: ultrawork] 全力执行模式：先列最短计划，再逐步完成；"
            "优先用 session_todos 跟踪；完成后汇报变更摘要。"
        ),
    },
    {
        "keywords": "深审,deepreview",
        "banner": (
            "[Intent: deepreview] 深度审查模式：只读分析，列出风险与建议，"
            "未经明确要求不要改文件。"
        ),
    },
]


def _parse_rules_env() -> list[dict[str, str]]:
    raw = os.getenv("BUTLER_INTENT_KEYWORDS", "").strip()
    if not raw:
        return list(_DEFAULT_RULES)
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            out: list[dict[str, str]] = []
            for row in data:
                if isinstance(row, dict) and row.get("keywords") and row.get("banner"):
                    out.append({
                        "keywords": str(row["keywords"]),
                        "banner": str(row["banner"]),
                    })
            if out:
                return out
    except json.JSONDecodeError:
        pass
    return list(_DEFAULT_RULES)


def intent_keywords_enabled() -> bool:
    raw = os.getenv("BUTLER_INTENT_KEYWORDS_OFF", "").strip().lower()
    return raw not in ("1", "true", "yes", "on")


def _keyword_hit(text: str, keywords_csv: str) -> bool:
    lowered = text.lower()
    for kw in keywords_csv.split(","):
        token = kw.strip().lower()
        if not token:
            continue
        if re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", lowered, re.UNICODE):
            return True
        if token in lowered:
            return True
    return False


def detect_intent_banner(user_text: str) -> str | None:
    """Return ephemeral system banner if any keyword matches; does not rewrite user text."""
    if not intent_keywords_enabled():
        return None
    text = (user_text or "").strip()
    if not text:
        return None
    banners: list[str] = []
    for rule in _parse_rules_env():
        if _keyword_hit(text, rule.get("keywords", "")):
            banners.append(str(rule.get("banner", "")).strip())
    if not banners:
        return None
    return "\n\n".join(banners)


def category_from_intent(user_text: str) -> str | None:
    """Map magic words to delegate category when user did not pass category explicitly."""
    lowered = (user_text or "").lower()
    if any(k in lowered for k in ("ulw", "ultrawork", "全力")):
        return "quick"
    if "deepreview" in lowered or "深审" in lowered:
        return "ultrabrain"
    return None
