"""Extract high-signal evidence lines before LLM compaction summary."""

from __future__ import annotations

import re
from typing import Any

from butler.env_parse import int_env

_SCORE_KEYWORDS = (
    "决定",
    "修复",
    "完成",
    "错误",
    "failed",
    "pytest",
    "TODO",
    "因为",
    "因此",
    "verify",
    "assert",
)
_PATH_HINT = re.compile(r"[\w./\\-]+\.(py|md|json|yaml|yml|sh)\b", re.I)
_SENT_SPLIT = re.compile(r"(?<=[。！？.!?])\s+|\n+")


def compact_evidence_lines_enabled() -> int:
    return int(int_env("BUTLER_COMPACT_EVIDENCE_LINES", 3, min=0, max=8))


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(parts)
    return str(content or "")


def _split_sentences(text: str) -> list[str]:
    chunks = _SENT_SPLIT.split(text.strip())
    return [c.strip() for c in chunks if c and c.strip()]


def extract_compact_evidence(middle: list[dict[str, Any]], *, max_lines: int | None = None) -> list[str]:
    """Score sentences from compressible middle; return top evidence lines."""
    limit = compact_evidence_lines_enabled() if max_lines is None else max(0, int(max_lines))
    if limit <= 0 or not middle:
        return []

    candidates: list[tuple[int, str]] = []
    for msg in middle:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = _content_to_text(msg.get("content"))
        if not content.strip():
            continue
        role_bonus = {"tool": 3, "assistant": 1, "user": 0}.get(role, 0)
        for sent in _split_sentences(content):
            if len(sent) < 12:
                continue
            score = role_bonus
            low = sent.lower()
            for kw in _SCORE_KEYWORDS:
                if kw in sent or kw in low:
                    score += 2
            if _PATH_HINT.search(sent):
                score += 2
            if re.search(r"\d", sent):
                score += 1
            candidates.append((score, sent[:280]))

    candidates.sort(key=lambda item: (-item[0], -len(item[1])))
    seen: set[str] = set()
    out: list[str] = []
    for score, line in candidates:
        if score < 2:
            continue
        key = line[:60].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= limit:
            break
    return out


def format_evidence_block(lines: list[str]) -> str:
    if not lines:
        return ""
    body = "\n".join(f"- {ln}" for ln in lines)
    return f"## Compact evidence (auto-extracted)\n{body}\n\n"


def append_evidence_to_summary(
    summary: str,
    middle: list[dict[str, Any]],
    diagnostics: dict[str, Any] | None = None,
) -> str:
    lines = extract_compact_evidence(middle)
    if diagnostics is not None:
        diagnostics["compaction_evidence_lines"] = len(lines)
    block = format_evidence_block(lines)
    if not block:
        return summary
    return block + summary


__all__ = [
    "append_evidence_to_summary",
    "compact_evidence_lines_enabled",
    "extract_compact_evidence",
    "format_evidence_block",
]
