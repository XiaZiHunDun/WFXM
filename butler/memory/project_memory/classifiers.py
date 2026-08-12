from __future__ import annotations

import os

from butler.defaults.env_defaults import MEMORY_AUTO_APPROVE_DEFAULT

from .constants import _SENSITIVE_PENDING_KEYWORDS, _SENSITIVE_PII_RE


def memory_auto_fact_enabled() -> bool:
    from butler.utilities.env_parse import env_truthy

    return bool(env_truthy("BUTLER_MEMORY_AUTO_FACT", default=True))


def memory_auto_approve_mode() -> str:
    raw = os.getenv("BUTLER_MEMORY_AUTO_APPROVE", MEMORY_AUTO_APPROVE_DEFAULT).strip().lower()
    if not raw or raw in ("0", "off", "false", "no"):
        return ""
    if raw in ("1", "all", "true", "yes", "on"):
        return "all"
    if raw == "correction":
        return "correction"
    return ""


def looks_correction_memory(content: str) -> bool:
    body = (content or "").strip()
    if not body:
        return False
    if body.startswith("[纠正]") or "category=correction" in body.lower():
        return True
    from butler.memory.project_memory_ops import looks_correction_intent_safe
    if looks_correction_intent_safe(body):
        return True
    lower = body.lower()
    markers = ("纠正", "刚才不对", "请记住", "以后请", "别再用", "不要再")
    return any(m in lower for m in markers)


def _looks_sensitive_memory(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    if _SENSITIVE_PII_RE.search(text):
        return True
    lower = text.lower()
    return any(kw in lower for kw in _SENSITIVE_PENDING_KEYWORDS)
