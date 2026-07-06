"""Parse pinned AGENTS.md sections for post-compaction re-injection (OpenClaw subset)."""

from __future__ import annotations

from butler.env_parse import int_env
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from typing import cast

logger = logging.getLogger(__name__)

_DEFAULT_SECTIONS = ("Session Startup", "Red Lines", "Every Session", "Safety")


def default_section_names() -> tuple[str, ...]:
    raw = os.getenv("BUTLER_POST_COMPACT_AGENTS_SECTIONS", "").strip()
    if not raw:
        return _DEFAULT_SECTIONS
    parts = tuple(s.strip() for s in raw.split(",") if s.strip())
    return parts or _DEFAULT_SECTIONS


def max_section_chars() -> int:
    try:
        return int(int_env("BUTLER_POST_COMPACT_AGENTS_MAX_CHARS", 2000, min=200, max=8000))
    except ValueError:
        return 2000


def _resolve_workspace() -> Path | None:
    from butler.core.agents_md_sections_ops import resolve_agents_md_workspace_safe

    return cast(Path | None, resolve_agents_md_workspace_safe())


def _substitute_date_placeholders(text: str, *, now_ms: float | None = None) -> str:
    if now_ms is None:
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
    date_stamp = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return (
        text.replace("YYYY-MM-DD", date_stamp)
        .replace("{{date}}", date_stamp)
        .replace("${date}", date_stamp)
    )


def extract_agents_md_sections(
    workspace: Path | None = None,
    *,
    section_names: tuple[str, ...] | None = None,
) -> str:
    """Return markdown block of requested ## sections from workspace AGENTS.md."""
    ws = workspace or _resolve_workspace()
    if ws is None:
        return ""
    path = ws / "AGENTS.md"
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("AGENTS.md read failed: %s", exc)
        return ""

    names = section_names or default_section_names()
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(raw))
    if not matches:
        return ""

    sections: list[str] = []
    cap = max_section_chars()
    used = 0
    name_set = {n.lower() for n in names}

    for i, match in enumerate(matches):
        title = match.group(1).strip()
        if title.lower() not in name_set:
            continue
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        if not body:
            continue
        block = f"## {title}\n{body}"
        block = _substitute_date_placeholders(block)
        if used + len(block) > cap:
            block = block[: max(0, cap - used)]
        sections.append(block)
        used += len(block)
        if used >= cap:
            break

    if not sections:
        return ""
    return "## AGENTS.md (pinned sections)\n" + "\n\n".join(sections)
