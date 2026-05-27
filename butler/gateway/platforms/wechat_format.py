"""WeChat message formatting and text splitting utilities.

Extracted from wechat_ilink.py. Contains pure functions for
converting markdown text into WeChat-friendly message chunks.
"""

from __future__ import annotations

import re
from typing import List

WECHAT_COPY_LINE_WIDTH = 120

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_RULE_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_FENCE_RE = re.compile(r"^```([^\n`]*)\s*$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

def _truncate_plain(text: str, max_length: int) -> list[str]:
    from butler.core.text_truncate import truncate_text, utf16_code_units, utf16_safe_slice

    if not text:
        return [""]
    if utf16_code_units(text) <= max_length:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest and utf16_code_units(rest) > max_length:
        piece, _ = truncate_text(rest, max_length, suffix="", prefer_newline=False)
        if not piece:
            piece = utf16_safe_slice(rest, max_length)
        chunks.append(piece)
        rest = rest[len(piece) :]
    if rest:
        chunks.append(rest)
    return chunks or [""]


def _split_table_row(line: str) -> List[str]:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def _rewrite_headers_for_wechat(line: str) -> str:
    match = _HEADER_RE.match(line)
    if not match:
        return line.rstrip()
    level = len(match.group(1))
    title = match.group(2).strip()
    if level == 1:
        return f"【{title}】"
    return f"**{title}**"


def _rewrite_table_block_for_wechat(lines: List[str]) -> str:
    if len(lines) < 2:
        return "\n".join(lines)
    headers = _split_table_row(lines[0])
    body_rows = [_split_table_row(line) for line in lines[2:] if line.strip()]
    if not headers or not body_rows:
        return "\n".join(lines)

    formatted_rows: List[str] = []
    for row in body_rows:
        pairs = []
        for idx, header in enumerate(headers):
            if idx >= len(row):
                break
            label = header or f"Column {idx + 1}"
            value = row[idx].strip()
            if value:
                pairs.append((label, value))
        if not pairs:
            continue
        if len(pairs) == 1:
            label, value = pairs[0]
            formatted_rows.append(f"- {label}: {value}")
            continue
        if len(pairs) == 2:
            label, value = pairs[0]
            other_label, other_value = pairs[1]
            formatted_rows.append(f"- {label}: {value}")
            formatted_rows.append(f"  {other_label}: {other_value}")
            continue
        summary = " | ".join(f"{label}: {value}" for label, value in pairs)
        formatted_rows.append(f"- {summary}")
    return "\n".join(formatted_rows) if formatted_rows else "\n".join(lines)


def _normalize_markdown_blocks(content: str) -> str:
    lines = content.splitlines()
    result: List[str] = []
    in_code_block = False
    blank_run = 0

    for raw_line in lines:
        line = raw_line.rstrip()
        if _FENCE_RE.match(line.strip()):
            in_code_block = not in_code_block
            result.append(line)
            blank_run = 0
            continue

        if in_code_block:
            result.append(line)
            continue

        if not line.strip():
            blank_run += 1
            if blank_run <= 1:
                result.append("")
            continue

        blank_run = 0
        result.append(line)

    return "\n".join(result).strip()


def _wrap_copy_friendly_lines_for_wechat(content: str) -> str:
    """Wrap long display lines that are hard to copy in WeChat clients."""
    if not content:
        return content

    wrapped: List[str] = []
    in_code_block = False

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if _FENCE_RE.match(stripped):
            in_code_block = not in_code_block
            wrapped.append(line)
            continue

        if (
            in_code_block
            or len(line) <= WECHAT_COPY_LINE_WIDTH
            or not stripped
            or stripped.startswith("|")
            or _TABLE_RULE_RE.match(stripped)
        ):
            wrapped.append(line)
            continue

        wrapped_lines = textwrap.wrap(
            line,
            width=WECHAT_COPY_LINE_WIDTH,
            break_long_words=False,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=True,
        )
        wrapped.extend(wrapped_lines or [line])

    return "\n".join(wrapped).strip()


def _split_markdown_blocks(content: str) -> List[str]:
    if not content:
        return []

    blocks: List[str] = []
    lines = content.splitlines()
    current: List[str] = []
    in_code_block = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if _FENCE_RE.match(line.strip()):
            if not in_code_block and current:
                blocks.append("\n".join(current).strip())
                current = []
            current.append(line)
            in_code_block = not in_code_block
            if not in_code_block:
                blocks.append("\n".join(current).strip())
                current = []
            continue

        if in_code_block:
            current.append(line)
            continue

        if not line.strip():
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def _split_delivery_units_for_wechat(content: str) -> List[str]:
    """Split formatted content into chat-friendly delivery units.

    WeChat can render Markdown, but chat readability is better when top-level
    line breaks become separate messages. Keep fenced code blocks intact and
    attach indented continuation lines to the previous top-level line so nested
    list items do not get torn apart.
    """
    units: List[str] = []

    for block in _split_markdown_blocks(content):
        if _FENCE_RE.match(block.splitlines()[0].strip()):
            units.append(block)
            continue

        current: List[str] = []
        for raw_line in block.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                if current:
                    units.append("\n".join(current).strip())
                    current = []
                continue

            is_continuation = bool(current) and raw_line.startswith((" ", "\t"))
            if is_continuation:
                current.append(line)
                continue

            if current:
                units.append("\n".join(current).strip())
            current = [line]

        if current:
            units.append("\n".join(current).strip())

    return [unit for unit in units if unit]


def _looks_like_chatty_line_for_wechat(line: str) -> bool:
    """Return True when a line looks like a standalone chat utterance."""
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) > 48:
        return False
    if line.startswith((" ", "\t")):
        return False
    if stripped.startswith((">", "-", "*", "【", "#", "|")):
        return False
    if _TABLE_RULE_RE.match(stripped):
        return False
    if re.match(r"^\*\*[^*]+\*\*$", stripped):
        return False
    if re.match(r"^\d+\.\s", stripped):
        return False
    return True


def _looks_like_heading_line_for_wechat(line: str) -> bool:
    """Return True when a short line behaves like a heading."""
    stripped = line.strip()
    if not stripped:
        return False
    if _HEADER_RE.match(stripped):
        return True
    return len(stripped) <= 24 and stripped.endswith((":", "："))


def _should_split_short_chat_block_for_wechat(block: str) -> bool:
    """Split only chat-like multiline blocks into separate bubbles."""
    lines = [line for line in block.splitlines() if line.strip()]
    if not 2 <= len(lines) <= 6:
        return False
    if _looks_like_heading_line_for_wechat(lines[0]):
        return False
    return all(_looks_like_chatty_line_for_wechat(line) for line in lines)


def _pack_markdown_blocks_for_wechat(content: str, max_length: int) -> List[str]:
    if len(content) <= max_length:
        return [content]

    packed: List[str] = []
    current = ""
    for block in _split_markdown_blocks(content):
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current:
            packed.append(current)
            current = ""
        if len(block) <= max_length:
            current = block
            continue
        packed.extend(_truncate_plain(block, max_length))
    if current:
        packed.append(current)
    return packed


def _split_text_for_wechat_delivery(
    content: str, max_length: int, split_per_line: bool = False,
) -> List[str]:
    """Split content into sequential WeChat messages.

    *compact* (default): Keep everything in a single message whenever it fits
    within the platform limit, even when the author used explicit line breaks.
    Only fall back to block-aware packing when the payload exceeds
    ``max_length``.

    *per_line* (``split_per_line=True``): Legacy behavior — top-level line
    breaks become separate chat messages; oversized units still use
    block-aware packing.

    The active mode is controlled via ``config.yaml`` ->
    ``platforms.wechat.extra.split_multiline_messages`` (``true`` / ``false``)
    or the env var ``WECHAT_SPLIT_MULTILINE_MESSAGES``.
    """
    if not content:
        return []
    if split_per_line:
        # Legacy: one message per top-level delivery unit.
        if len(content) <= max_length and "\n" not in content:
            return [content]
        chunks: List[str] = []
        for unit in _split_delivery_units_for_wechat(content):
            if len(unit) <= max_length:
                chunks.append(unit)
                continue
            chunks.extend(_pack_markdown_blocks_for_wechat(unit, max_length))
        return [c for c in chunks if c] or [content]

    # Compact (default): single message when under the limit — unless the
    # content looks like a short chatty exchange, in which case split into
    # separate bubbles for a more natural chat feel.
    if len(content) <= max_length:
        return (
            [u for u in _split_delivery_units_for_wechat(content) if u]
            if _should_split_short_chat_block_for_wechat(content)
            else [content]
        )
    return _pack_markdown_blocks_for_wechat(content, max_length) or [content]
