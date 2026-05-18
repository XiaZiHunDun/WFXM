#!/usr/bin/env python3
"""Butler tool: apply V4A patches using fuzzy matching."""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path
from typing import Any, List

from butler.tools.code_tools import _lint_file, _resolve_path
from butler.tools.fuzzy_match import format_no_match_hint, fuzzy_find_and_replace
from butler.tools.patch_parser import (
    OperationType,
    PatchOperation,
    parse_v4a_patch,
)
from butler.tools.registry import register_tool


def _count_occurrences(text: str, pattern: str) -> int:
    count = 0
    start = 0
    while True:
        pos = text.find(pattern, start)
        if pos == -1:
            break
        count += 1
        start = pos + 1
    return count


def _resolve_op_path(file_path: str) -> Path:
    return _resolve_path(file_path)


def _validate_operations(operations: List[PatchOperation]) -> List[str]:
    errors: List[str] = []
    for op in operations:
        if op.operation == OperationType.UPDATE:
            p = _resolve_op_path(op.file_path)
            if not p.is_file():
                errors.append(f"{op.file_path}: file not found for update")
                continue
            try:
                simulated = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                errors.append(f"{op.file_path}: cannot read ({e})")
                continue
            for hunk in op.hunks:
                search_lines = [l.content for l in hunk.lines if l.prefix in (" ", "-")]
                if not search_lines:
                    if hunk.context_hint:
                        occ = _count_occurrences(simulated, hunk.context_hint)
                        if occ == 0:
                            errors.append(
                                f"{op.file_path}: addition-only hunk context hint "
                                f"{hunk.context_hint!r} not found"
                            )
                        elif occ > 1:
                            errors.append(
                                f"{op.file_path}: addition-only hunk context hint "
                                f"{hunk.context_hint!r} is ambiguous ({occ} occurrences)"
                            )
                    continue
                search_pattern = "\n".join(search_lines)
                replace_lines = [l.content for l in hunk.lines if l.prefix in (" ", "+")]
                replacement = "\n".join(replace_lines)
                new_simulated, count, _s, match_error = fuzzy_find_and_replace(
                    simulated, search_pattern, replacement, replace_all=False
                )
                if count == 0:
                    label = f"{hunk.context_hint!r}" if hunk.context_hint else "(no hint)"
                    msg = (
                        f"{op.file_path}: hunk {label} not found"
                        + (f" — {match_error}" if match_error else "")
                    )
                    msg += format_no_match_hint(match_error, count, search_pattern, simulated)
                    errors.append(msg)
                else:
                    simulated = new_simulated

        elif op.operation == OperationType.DELETE:
            p = _resolve_op_path(op.file_path)
            if not p.is_file():
                errors.append(f"{op.file_path}: file not found for deletion")

        elif op.operation == OperationType.MOVE:
            src = _resolve_op_path(op.file_path)
            if not src.is_file():
                errors.append(f"{op.file_path}: source file not found for move")
            if op.new_path:
                dst = _resolve_op_path(op.new_path)
                if dst.exists():
                    errors.append(
                        f"{op.new_path}: destination already exists — move would overwrite"
                    )

    return errors


def _apply_update(op: PatchOperation) -> tuple[bool, str]:
    p = _resolve_op_path(op.file_path)
    if not p.is_file():
        return False, f"Cannot read file: not found ({op.file_path})"
    try:
        new_content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False, f"Cannot read file as UTF-8: {op.file_path}"
    current_content = new_content

    for hunk in op.hunks:
        search_lines: List[str] = []
        replace_lines: List[str] = []
        for line in hunk.lines:
            if line.prefix == " ":
                search_lines.append(line.content)
                replace_lines.append(line.content)
            elif line.prefix == "-":
                search_lines.append(line.content)
            elif line.prefix == "+":
                replace_lines.append(line.content)

        if search_lines:
            search_pattern = "\n".join(search_lines)
            replacement = "\n".join(replace_lines)
            new_content, count, _s, error = fuzzy_find_and_replace(
                new_content, search_pattern, replacement, replace_all=False
            )
            if error and count == 0:
                if hunk.context_hint:
                    hint_pos = new_content.find(hunk.context_hint)
                    if hint_pos != -1:
                        window_start = max(0, hint_pos - 500)
                        window_end = min(len(new_content), hint_pos + 2000)
                        window = new_content[window_start:window_end]
                        window_new, count2, _s2, err2 = fuzzy_find_and_replace(
                            window, search_pattern, replacement, replace_all=False
                        )
                        if count2 > 0:
                            new_content = (
                                new_content[:window_start]
                                + window_new
                                + new_content[window_end:]
                            )
                            error = None
                if error:
                    err_msg = f"Could not apply hunk: {error}"
                    err_msg += format_no_match_hint(error, 0, search_pattern, new_content)
                    return False, err_msg
        else:
            insert_text = "\n".join(replace_lines)
            if hunk.context_hint:
                occ = _count_occurrences(new_content, hunk.context_hint)
                if occ == 0:
                    new_content = new_content.rstrip("\n") + "\n" + insert_text + "\n"
                elif occ > 1:
                    return False, (
                        f"Addition-only hunk: context hint {hunk.context_hint!r} is ambiguous "
                        f"({occ} occurrences) — provide a more unique hint"
                    )
                else:
                    hint_pos = new_content.find(hunk.context_hint)
                    eol = new_content.find("\n", hint_pos)
                    if eol != -1:
                        new_content = (
                            new_content[: eol + 1]
                            + insert_text
                            + "\n"
                            + new_content[eol + 1 :]
                        )
                    else:
                        new_content = new_content + "\n" + insert_text
            else:
                new_content = new_content.rstrip("\n") + "\n" + insert_text + "\n"

    try:
        p.write_text(new_content, encoding="utf-8")
    except OSError as e:
        return False, str(e)

    diff = "".join(
        difflib.unified_diff(
            current_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{op.file_path}",
            tofile=f"b/{op.file_path}",
        )
    )
    return True, diff


def _apply_add(op: PatchOperation) -> tuple[bool, str]:
    content_lines: List[str] = []
    for hunk in op.hunks:
        for line in hunk.lines:
            if line.prefix == "+":
                content_lines.append(line.content)
    content = "\n".join(content_lines)
    p = _resolve_op_path(op.file_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as e:
        return False, str(e)

    diff = f"--- /dev/null\n+++ b/{op.file_path}\n" + "\n".join(f"+{ln}" for ln in content_lines)
    return True, diff


def _apply_delete(op: PatchOperation) -> tuple[bool, str]:
    p = _resolve_op_path(op.file_path)
    if not p.is_file():
        return False, f"Cannot delete {op.file_path}: file not found"
    try:
        removed = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return False, str(e)
    try:
        p.unlink()
    except OSError as e:
        return False, str(e)

    removed_lines = removed.splitlines(keepends=True)
    diff = "".join(
        difflib.unified_diff(
            removed_lines,
            [],
            fromfile=f"a/{op.file_path}",
            tofile="/dev/null",
        )
    )
    return True, diff or f"# Deleted: {op.file_path}"


def _apply_move(op: PatchOperation) -> tuple[bool, str]:
    src = _resolve_op_path(op.file_path)
    dst = _resolve_op_path(op.new_path or "")
    if not op.new_path:
        return False, "MOVE missing destination path"
    if not src.is_file():
        return False, f"Source not found: {op.file_path}"
    if dst.exists():
        return False, f"Destination already exists: {op.new_path}"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except OSError as e:
        return False, str(e)
    return True, f"# Moved: {op.file_path} -> {op.new_path}"


def _paths_to_lint(operations: List[PatchOperation], files_modified: List[str]) -> List[Path]:
    """Paths that were written or overwritten (excluding deletions)."""
    out: List[Path] = []
    seen: set[str] = set()
    for label in files_modified:
        if " -> " in label:
            _src, dst = label.split(" -> ", 1)
            p = _resolve_op_path(dst.strip())
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                out.append(p)
        else:
            p = _resolve_op_path(label)
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                out.append(p)
    for op in operations:
        if op.operation == OperationType.ADD:
            p = _resolve_op_path(op.file_path)
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


@register_tool(
    name="patch",
    description=(
        "使用 V4A 补丁格式批量修改文件。支持 Update/Add/Delete/Move 操作。"
        "比 edit_file 更适合多处修改。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "patch_content": {
                "type": "string",
                "description": "V4A 格式的补丁内容",
            },
        },
        "required": ["patch_content"],
    },
    category="code",
)
def apply_patch(patch_content: str) -> dict[str, Any]:
    operations, parse_err = parse_v4a_patch(patch_content)
    if parse_err:
        return {
            "success": False,
            "files_modified": [],
            "files_created": [],
            "files_deleted": [],
            "errors": [parse_err],
        }

    if not operations:
        return {
            "success": True,
            "files_modified": [],
            "files_created": [],
            "files_deleted": [],
            "errors": [],
            "message": "Empty patch (no operations).",
        }

    validation_errors = _validate_operations(operations)
    if validation_errors:
        return {
            "success": False,
            "files_modified": [],
            "files_created": [],
            "files_deleted": [],
            "errors": validation_errors,
        }

    files_modified: List[str] = []
    files_created: List[str] = []
    files_deleted: List[str] = []
    errors: List[str] = []

    for op in operations:
        try:
            if op.operation == OperationType.ADD:
                ok, _diff = _apply_add(op)
                if ok:
                    files_created.append(op.file_path)
                else:
                    errors.append(f"Failed to add {op.file_path}: {_diff}")

            elif op.operation == OperationType.DELETE:
                ok, _diff = _apply_delete(op)
                if ok:
                    files_deleted.append(op.file_path)
                else:
                    errors.append(f"Failed to delete {op.file_path}: {_diff}")

            elif op.operation == OperationType.MOVE:
                ok, _diff = _apply_move(op)
                if ok:
                    files_modified.append(f"{op.file_path} -> {op.new_path}")
                else:
                    errors.append(f"Failed to move {op.file_path}: {_diff}")

            elif op.operation == OperationType.UPDATE:
                ok, msg = _apply_update(op)
                if ok:
                    files_modified.append(op.file_path)
                else:
                    errors.append(f"Failed to update {op.file_path}: {msg}")

        except Exception as e:
            errors.append(f"Error processing {op.file_path}: {e}")

    lint_results: dict[str, str] = {}
    if not errors:
        for p in _paths_to_lint(operations, files_modified):
            if not p.is_file():
                continue
            err = _lint_file(p)
            if err:
                lint_results[str(p)] = err

    result: dict[str, Any] = {
        "success": len(errors) == 0,
        "files_modified": files_modified,
        "files_created": files_created,
        "files_deleted": files_deleted,
        "errors": errors,
    }
    if lint_results:
        result["lint_errors"] = lint_results
        result["warning"] = "部分已修改文件存在语法问题，请检查"

    return result
