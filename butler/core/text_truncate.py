"""UTF-16-safe text truncation (LobeHub truncateToolResult subset)."""

from __future__ import annotations

import os

from butler.env_parse import env_truthy


def utf16_safe_truncate_enabled() -> bool:
    return env_truthy("BUTLER_UTF16_SAFE_TRUNCATE", default=True)


def utf16_code_units(text: str) -> int:
    """Count UTF-16 code units (BMP=1, supplementary=2)."""
    n = 0
    for ch in text or "":
        n += 2 if ord(ch) > 0xFFFF else 1
    return n


def utf16_safe_slice(text: str, max_units: int) -> str:
    """Return prefix of *text* with at most *max_units* UTF-16 code units."""
    if max_units <= 0:
        return ""
    s = text or ""
    if utf16_code_units(s) <= max_units:
        return s
    out: list[str] = []
    units = 0
    for ch in s:
        need = 2 if ord(ch) > 0xFFFF else 1
        if units + need > max_units:
            break
        out.append(ch)
        units += need
    return "".join(out)


def truncate_text(
    text: str,
    max_chars: int,
    *,
    suffix: str = "",
    prefer_newline: bool = True,
) -> tuple[str, bool]:
    """Truncate for display/spill preview; returns (text, was_truncated)."""
    if max_chars <= 0:
        return "", bool(text)
    s = text or ""
    if not utf16_safe_truncate_enabled():
        if len(s) <= max_chars:
            return s, False
        cut = max_chars
        if prefer_newline:
            chunk = s[:max_chars]
            last_nl = chunk.rfind("\n")
            if last_nl > max_chars // 2:
                cut = last_nl
        return s[:cut] + suffix, True

    if utf16_code_units(s) <= max_chars:
        return s, False
    base = utf16_safe_slice(s, max_chars)
    if prefer_newline and base:
        last_nl = base.rfind("\n")
        if last_nl > len(base) // 2:
            base = base[:last_nl]
    return base + suffix, True
