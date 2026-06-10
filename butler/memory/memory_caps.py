"""Size caps for project MEMORY.md (Claude Code memdir truncateEntrypointContent)."""

from __future__ import annotations

from typing import Tuple

from butler.memory_settings import resolve_memory_config


def memory_index_caps() -> dict[str, int]:
    cfg = resolve_memory_config()
    return {"max_lines": cfg.max_lines, "max_bytes": cfg.max_bytes}


def truncate_memory_text(text: str) -> Tuple[str, bool]:
    """Line cap first, then byte cap at last newline (matches Claude Code memdir)."""
    caps = memory_index_caps()
    trimmed = (text or "").strip()
    if not trimmed:
        return "", False

    content_lines = trimmed.split("\n")
    line_count = len(content_lines)
    byte_count = len(trimmed.encode("utf-8"))
    max_lines = caps["max_lines"]
    max_bytes = caps["max_bytes"]

    was_line_truncated = bool(max_lines and line_count > max_lines)
    was_byte_truncated = bool(max_bytes and byte_count > max_bytes)

    if not was_line_truncated and not was_byte_truncated:
        return trimmed, False

    truncated = (
        "\n".join(content_lines[:max_lines])
        if was_line_truncated
        else trimmed
    )

    if max_bytes and len(truncated.encode("utf-8")) > max_bytes:
        cut_at = truncated.rfind("\n", 0, max_bytes)
        truncated = truncated[: cut_at if cut_at > 0 else max_bytes]

    if was_byte_truncated and not was_line_truncated:
        reason = f"{byte_count} bytes (limit: {max_bytes})"
    elif was_line_truncated and not was_byte_truncated:
        reason = f"{line_count} lines (limit: {max_lines})"
    else:
        reason = f"{line_count} lines and {byte_count} bytes"

    warning = (
        f"\n\n> WARNING: MEMORY.md is {reason}. "
        "Only part was loaded. Keep index entries short; move detail into topic files."
    )
    return truncated.rstrip() + warning, True
