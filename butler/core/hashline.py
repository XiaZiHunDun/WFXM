"""Line-level edit anchors with per-line hash (OMO hashline-core subset, stdlib only)."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

_BASE_CHARS = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "+-^*[]{}()<>?@#$%&!~`|\\/_=.;:,"
)
_HASHLINE_DICT = (_BASE_CHARS * 8)[:256]

_RE_SIGNIFICANT = re.compile(r"[\w]", re.UNICODE)
_HASHLINE_LINE_RE = re.compile(r"^(\d+)#([^|]+)\|(.*)$")


def hashline_read_enabled() -> bool:
    from butler.env_parse import env_truthy

    return bool(env_truthy("BUTLER_HASHLINE_READ", default=False))
def hashline_patch_enabled() -> bool:
    from butler.env_parse import env_truthy

    return bool(env_truthy("BUTLER_HASHLINE_PATCH", default=True))
def compute_line_hash(line_number: int, content: str) -> str:
    normalized = content.replace("\r", "").rstrip()
    seed = 0 if _RE_SIGNIFICANT.search(normalized) else int(line_number)
    digest = hashlib.sha256(f"{seed}:{normalized}".encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % 256
    return _HASHLINE_DICT[index]


def format_hash_line(line_number: int, content: str) -> str:
    h = compute_line_hash(line_number, content)
    return f"{line_number}#{h}|{content}"


def format_hash_lines(text: str) -> str:
    if not text:
        return ""
    lines = text.split("\n")
    return "\n".join(format_hash_line(i + 1, line) for i, line in enumerate(lines))


def format_read_output(path: Path, lines: list[str], start_line: int) -> str:
    if hashline_read_enabled():
        return "\n".join(
            format_hash_line(start_line + i, line)
            for i, line in enumerate(lines)
        )
    return "\n".join(f"{start_line + i:6}|{line}" for i, line in enumerate(lines))
def verify_line_anchors(path: Path, anchors: list[tuple[int, str]]) -> dict[str, Any] | None:
    """Verify (line_no, hash) pairs against current file; return error dict or None."""
    if not hashline_patch_enabled() or not anchors:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": str(exc), "code": "HASHLINE_READ_FAIL"}
    file_lines = text.splitlines()
    mismatches: list[dict[str, Any]] = []
    for line_no, expected_hash in anchors:
        idx = line_no - 1
        if idx < 0 or idx >= len(file_lines):
            mismatches.append({
                "line": line_no,
                "expected": expected_hash,
                "reason": "line_out_of_range",
            })
            continue
        actual = compute_line_hash(line_no, file_lines[idx])
        if actual != expected_hash:
            mismatches.append({
                "line": line_no,
                "expected": expected_hash,
                "actual": actual,
                "preview": file_lines[idx][:80],
            })
    if not mismatches:
        return None
    return {
        "error": "HASHLINE_MISMATCH: file changed since read; re-read with read_file",
        "code": "HASHLINE_MISMATCH",
        "mismatches": mismatches[:5],
    }


def extract_anchors_from_old_string(old_string: str) -> list[tuple[int, str]]:
    anchors: list[tuple[int, str]] = []
    for line in old_string.splitlines():
        m = _HASHLINE_LINE_RE.match(line)
        if m:
            anchors.append((int(m.group(1)), m.group(2)))
    return anchors
