"""Strip leaked thinking/tool XML from model output (Hermes run_agent L3539+)."""

from __future__ import annotations

import re

# Stream filter: quick tag removal before display
STREAM_TAG_FILTER = re.compile(
    r"</?(?:redacted_thinking|think|thinking|reasoning|thought|tool_call|tool_calls)>",
    re.IGNORECASE,
)


def strip_think_blocks(content: str) -> str:
    """Return visible text only; reasoning blocks removed."""
    if not content:
        return ""
    text = content
    for tag in (
        "redacted_thinking",
        "thinking",
        "reasoning",
        "REASONING_SCRATCHPAD",
        "thought",
    ):
        text = re.sub(
            rf"<{tag}>.*?</{tag}>",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    for tc_name in (
        "tool_call",
        "tool_calls",
        "tool_result",
        "function_call",
        "function_calls",
    ):
        text = re.sub(
            rf"<{tc_name}\b[^>]*>.*?</{tc_name}>",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    text = re.sub(
        r"(?:(?<=^)|(?<=[\n\r.!?:]))[ \t]*"
        r"<function\b[^>]*\bname\s*=[^>]*>"
        r"(?:(?:(?!</function>).)*)</function>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r"(?:^|\n)[ \t]*<(?:think|thinking|reasoning|thought|REASONING_SCRATCHPAD)\b[^>]*>.*$",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r"</?(?:think|thinking|reasoning|thought|REASONING_SCRATCHPAD)>\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</(?:tool_call|tool_calls|tool_result|function_call|function_calls|function)>\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text


def has_visible_content(content: str | None) -> bool:
    """True if any non-whitespace remains after think stripping."""
    if not content:
        return False
    return bool(strip_think_blocks(content).strip())


def extract_thinking_to_reasoning(content: str, existing: str | None = None) -> tuple[str | None, str | None]:
    """Pull closed redacted_thinking blocks into reasoning; return (content, reasoning)."""
    if not content:
        return content, existing
    parts = re.findall(
        r"<think>(.*?)</think>",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    reasoning = existing
    if parts:
        extracted = "\n".join(p.strip() for p in parts if p.strip())
        if extracted:
            reasoning = (reasoning + "\n" + extracted) if reasoning else extracted
    visible = strip_think_blocks(
        re.sub(
            r"<think>.*?</think>",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
    )
    return visible or None, reasoning


def sanitize_stream_delta(delta: str) -> str:
    """Filter tags from a single streaming token."""
    if not delta:
        return ""
    return STREAM_TAG_FILTER.sub("", delta)
