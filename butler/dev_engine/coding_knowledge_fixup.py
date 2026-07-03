"""Re-activate coding knowledge after verify_fail (FIX phase, P1)."""

from __future__ import annotations

import re
from typing import Any

_VERIFY_KEYWORDS = frozenset(
    {
        "verify",
        "verify_fail",
        "pytest",
        "assert",
        "assertion",
        "failed",
        "error",
        "test",
    }
)


def keywords_from_verify_fail(verify_result: Any, *, extra: list[str] | None = None) -> list[str]:
    """Build retrieval keywords from verify diagnostics and output tail."""
    tokens: list[str] = []
    for diag in getattr(verify_result, "diagnostics", None) or []:
        for field in (getattr(diag, "message", ""), getattr(diag, "rule", ""), getattr(diag, "source", "")):
            tokens.extend(_tokenize(str(field or "")))
    tokens.extend(_tokenize(str(getattr(verify_result, "output_tail", "") or "")))
    for kw in extra or []:
        tokens.extend(_tokenize(kw))
    for kw in _VERIFY_KEYWORDS:
        tokens.append(kw)
    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out[:48]


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", text) if len(t) > 1]


def reactivate_coding_knowledge_on_verify_fail(state: Any) -> dict[str, Any]:
    """Re-run process_task after verify_fail and refresh DevState guidance."""
    verify_result = getattr(state, "verify_result", None)
    if verify_result is None or getattr(verify_result, "passed", False):
        return {"reactivated": False, "reason": "verify_passed"}

    base_keywords = list(getattr(state, "_delegate_keywords", None) or [])
    extra = [str(getattr(state, "task_description", "") or "")]
    keywords = keywords_from_verify_fail(verify_result, extra=extra)
    for kw in base_keywords:
        if kw and kw not in keywords:
            keywords.append(kw)

    from butler.dev_engine.coding_knowledge_fixup_ops import reactivate_coding_knowledge_core_safe

    payload = reactivate_coding_knowledge_core_safe(state, keywords)
    if payload is not None:
        return payload
    return {"reactivated": False, "reason": "reactivation_skipped"}


__all__ = [
    "keywords_from_verify_fail",
    "reactivate_coding_knowledge_on_verify_fail",
]
