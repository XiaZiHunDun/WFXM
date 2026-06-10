"""Large-file read summary + sectional hints (Traycer read_partial subset)."""

from __future__ import annotations

from butler.env_parse import int_env
import os
import re
from typing import Any


def read_summary_threshold_lines() -> int:
    try:
        return max(50, int_env("BUTLER_READ_FILE_SUMMARY_THRESHOLD", 400))
    except ValueError:
        return 400


def _heading_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith("#"):
        return True
    if re.match(r"^(class|def|async def|function|export)\s+", s):
        return True
    if re.match(r"^[\w.]+\s*=\s*", s) and len(s) < 120:
        return True
    return False


def build_large_file_summary(
    path: str,
    lines: list[str],
    *,
    max_sections: int = 24,
) -> dict[str, Any]:
    """Structured overview for first-pass reads of huge files."""
    total = len(lines)
    sections: list[dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        if not _heading_line(line):
            continue
        preview = line.strip()[:160]
        sections.append({"line": i, "preview": preview})
        if len(sections) >= max_sections:
            break

    return {
        "mode": "summary",
        "path": path,
        "total_lines": total,
        "sections": sections,
        "read_contract": {
            "offset": 1,
            "limit": 200,
            "hint": "使用 read_file 的 offset（1 起）与 limit 分段读取正文；首次大文件已省略全文。",
        },
    }


def format_summary_message(summary: dict[str, Any]) -> str:
    total = summary.get("total_lines", 0)
    path = summary.get("path", "")
    sections = summary.get("sections") or []
    lines_out = [
        "[read_file 大文件摘要]",
        f"路径: {path}",
        f"总行数: {total}",
        "",
        "章节/锚点（行号 | 预览）:",
    ]
    if not sections:
        lines_out.append("  （未检测到标题或符号锚点，建议 offset=1 limit=200 从头读）")
    else:
        for sec in sections:
            lines_out.append(f"  L{sec.get('line')}: {sec.get('preview', '')}")
    contract = summary.get("read_contract") or {}
    hint = contract.get("hint") or ""
    lines_out.extend([
        "",
        f"分段读取: offset={contract.get('offset', 1)} limit={contract.get('limit', 200)}",
        hint,
    ])
    return "\n".join(lines_out)


__all__ = [
    "build_large_file_summary",
    "format_summary_message",
    "read_summary_threshold_lines",
]
