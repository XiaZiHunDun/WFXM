"""Parse plan markdown and sync structured plan_step rows to transcript."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_SECTION_KIND: dict[str, str] = {
    "已知事实": "fact",
    "事实": "fact",
    "facts": "fact",
    "待验证": "hypothesis",
    "假设": "hypothesis",
    "hypothesis": "hypothesis",
    "步骤": "step",
    "实施步骤": "step",
    "steps": "step",
    "风险": "risk",
    "风险与验收": "risk",
    "risks": "risk",
}

_INLINE_TAG = re.compile(
    r"\[(fact|hypothesis|step|risk)\]\s*:?\s*",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^[\s]*[-*]\s+(?P<body>.+)$")
_HEADING = re.compile(r"^#{1,4}\s+(?P<title>.+)$")


def _normalize_section_title(title: str) -> str:
    raw = str(title or "").strip()
    raw = re.sub(r"^[0-9]+[.)]\s*", "", raw)
    return raw.lower()


def _kind_for_section(title: str) -> str:
    norm = _normalize_section_title(title)
    for key, kind in _SECTION_KIND.items():
        if key.lower() in norm:
            return kind
    return "step"


def _parse_bullet(body: str, default_kind: str) -> dict[str, str]:
    text = str(body or "").strip()
    kind = default_kind
    m = _INLINE_TAG.match(text)
    if m:
        kind = m.group(1).lower()
        text = _INLINE_TAG.sub("", text, count=1).strip()
    assumption = ""
    evidence = ""
    if "假设：" in text or "假设:" in text:
        parts = re.split(r"假设[：:]", text, maxsplit=1)
        text = parts[0].strip()
        assumption = parts[1].strip() if len(parts) > 1 else ""
    if "证据：" in text or "证据:" in text:
        parts = re.split(r"证据[：:]", text, maxsplit=1)
        head = parts[0].strip()
        evidence = parts[1].strip() if len(parts) > 1 else ""
        text = head
    title = text[:120]
    return {
        "title": title,
        "step_kind": kind,
        "detail": text[:300],
        "assumption": assumption[:300],
        "evidence": evidence[:300],
    }


def extract_plan_steps_from_markdown(content: str) -> list[dict[str, str]]:
    """Heuristic extract of fact/hypothesis/step/risk bullets from plan markdown."""
    lines = str(content or "").splitlines()
    current_kind = "step"
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in lines:
        hm = _HEADING.match(line.strip())
        if hm:
            current_kind = _kind_for_section(hm.group("title"))
            continue
        bm = _BULLET.match(line)
        if not bm:
            continue
        step = _parse_bullet(bm.group("body"), current_kind)
        key = f"{step['step_kind']}|{step['title']}"
        if not step["title"] or key in seen:
            continue
        seen.add(key)
        out.append(step)
    return out[:48]


def sync_plan_file_to_transcript(
    session_key: str,
    path: str,
    content: str,
) -> int:
    """If plan mode + writable plan path, record extracted plan_step rows."""
    from butler.plan.markdown_sync_ops import sync_plan_file_to_transcript_safe

    return int(sync_plan_file_to_transcript_safe(session_key, path, content))


__all__ = [
    "extract_plan_steps_from_markdown",
    "sync_plan_file_to_transcript",
]
