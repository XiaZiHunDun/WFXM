"""File operation tools for the Butler."""

from __future__ import annotations

import os
from pathlib import Path

from butler.tools.output_limits import truncate_output
from butler.tools.registry import register_tool

_DEFAULT_WINDOW = 150
_MAX_ENTRIES = 200


@register_tool(
    name="read_file",
    description="读取指定文件的内容",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径（相对于项目目录或绝对路径）"},
            "offset": {"type": "integer", "description": "起始行号（从1开始），可选"},
            "limit": {"type": "integer", "description": "读取行数，可选"},
        },
        "required": ["path"],
    },
    category="file",
)
def read_file(path: str, offset: int = 0, limit: int = 0) -> dict:
    resolved = _resolve_path(path)
    if not resolved.exists():
        return {"error": f"文件不存在: {path}"}
    if not resolved.is_file():
        return {"error": f"不是文件: {path}"}

    try:
        text = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"error": f"无法读取（非文本文件）: {path}"}

    from butler.tools.file_state import record_read

    explicit_window = offset > 0 or limit > 0
    lines = text.splitlines(keepends=True)
    total_lines = len(lines)

    applied_default_window = False
    if not explicit_window and total_lines > _DEFAULT_WINDOW:
        lines = lines[:_DEFAULT_WINDOW]
        applied_default_window = True

    if offset > 0:
        lines = lines[offset - 1 :]
    if limit > 0:
        lines = lines[:limit]

    partial = explicit_window or applied_default_window
    record_read("main", str(resolved.resolve()), partial=partial)

    content = "".join(lines)
    if applied_default_window:
        content += (
            f"\n--- 文件共 {total_lines} 行，已显示前 {_DEFAULT_WINDOW} 行。"
            f"使用 offset/limit 参数查看其他部分 ---"
        )

    content, _was_truncated = truncate_output(content)
    if content == "":
        content = "(文件为空)"

    return {"path": str(resolved), "content": content, "total_lines": total_lines}


@register_tool(
    name="write_file",
    description="写入内容到指定文件（覆盖或创建）",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的内容"},
        },
        "required": ["path", "content"],
    },
    category="file",
)
def write_file(path: str, content: str) -> dict:
    resolved = _resolve_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")

    from butler.tools.file_state import note_write

    note_write("main", str(resolved.resolve()))

    return {"success": True, "path": str(resolved), "bytes": len(content.encode("utf-8"))}


@register_tool(
    name="list_directory",
    description="列出目录内容",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径"},
            "recursive": {"type": "boolean", "description": "是否递归列出子目录，默认 false"},
            "max_depth": {"type": "integer", "description": "递归最大深度，默认 2"},
        },
        "required": ["path"],
    },
    category="file",
)
def list_directory(path: str, recursive: bool = False, max_depth: int = 2) -> dict:
    resolved = _resolve_path(path)
    if not resolved.exists():
        return {"error": f"目录不存在: {path}"}
    if not resolved.is_dir():
        return {"error": f"不是目录: {path}"}

    entries = []
    _collect_entries(resolved, entries, recursive, max_depth, 0)
    truncated_note = ""
    if len(entries) > _MAX_ENTRIES:
        truncated_note = f"条目超过 {_MAX_ENTRIES}，仅显示前 {_MAX_ENTRIES} 项。"
        entries = entries[:_MAX_ENTRIES]
        entries.append({"name": truncated_note, "type": "info"})
    if not entries:
        entries = [{"name": "(目录为空)", "type": "info"}]
    return {"path": str(resolved), "entries": entries}


def _collect_entries(dirpath: Path, entries: list, recursive: bool, max_depth: int, depth: int) -> None:
    try:
        for item in sorted(dirpath.iterdir()):
            if item.name.startswith("."):
                continue
            entry = {
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            }
            if item.is_dir() and recursive and depth < max_depth:
                children: list = []
                _collect_entries(item, children, recursive, max_depth, depth + 1)
                entry["children"] = children
            entries.append(entry)
    except PermissionError:
        entries.append({"name": "(permission denied)", "type": "error"})


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    from butler.core.project_manager import project_manager

    if project_manager.current_project:
        proj = project_manager.get_project(project_manager.current_project)
        if proj:
            return proj.workspace / path
    return Path.cwd() / path
