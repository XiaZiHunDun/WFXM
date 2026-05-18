"""Central defaults and helpers for truncating tool output (Hermes-style)."""

from __future__ import annotations

DEFAULT_MAX_BYTES = 50_000
DEFAULT_MAX_LINES = 2000
DEFAULT_MAX_LINE_LENGTH = 2000

_LINE_TRUNC_SUFFIX = "... [truncated]"


def get_output_limits() -> dict[str, int]:
    """Return resolved limits: max_bytes, max_lines, max_line_length."""
    return {
        "max_bytes": DEFAULT_MAX_BYTES,
        "max_lines": DEFAULT_MAX_LINES,
        "max_line_length": DEFAULT_MAX_LINE_LENGTH,
    }


def get_max_bytes() -> int:
    return get_output_limits()["max_bytes"]


def get_max_lines() -> int:
    return get_output_limits()["max_lines"]


def get_max_line_length() -> int:
    return get_output_limits()["max_line_length"]


def truncate_output(
    text: str,
    max_bytes: int | None = None,
    max_lines: int | None = None,
    max_line_length: int | None = None,
) -> tuple[str, bool]:
    """Truncate text: per-line length, then line count, then UTF-8 byte size."""
    lim = get_output_limits()
    mb = lim["max_bytes"] if max_bytes is None else max(1, int(max_bytes))
    ml = lim["max_lines"] if max_lines is None else max(1, int(max_lines))
    mll = lim["max_line_length"] if max_line_length is None else max(1, int(max_line_length))

    was_truncated = False

    # 1) Per-line character cap
    lines = text.split("\n")
    new_lines: list[str] = []
    for line in lines:
        if len(line) <= mll:
            new_lines.append(line)
            continue
        budget = mll - len(_LINE_TRUNC_SUFFIX)
        if budget <= 0:
            new_lines.append(_LINE_TRUNC_SUFFIX[:mll])
        else:
            new_lines.append(line[:budget] + _LINE_TRUNC_SUFFIX)
        was_truncated = True
    result = "\n".join(new_lines)

    # 2) Line count
    result_lines = result.split("\n")
    if len(result_lines) > ml:
        result = "\n".join(result_lines[:ml])
        was_truncated = True

    # 3) UTF-8 byte cap
    encoded = result.encode("utf-8")
    if len(encoded) > mb:
        cut = encoded[:mb]
        result = cut.decode("utf-8", errors="ignore")
        was_truncated = True

    return result, was_truncated
