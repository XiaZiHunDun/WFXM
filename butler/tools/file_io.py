"""File I/O tool implementations (read, write, delete, patch)."""

from __future__ import annotations

import json
import os
import stat as stat_module
import time
from pathlib import Path
from typing import Any

from butler.core.hashline import (
    format_hash_line,
    format_read_output,
    hashline_read_enabled,
)
from butler.core.read_file_partial import (
    build_large_file_summary,
    format_summary_message,
    read_summary_threshold_lines,
)
from butler.core.read_state import (
    normalize_quotes,
    record_read_state,
    require_read_before_edit,
)
from butler.execution_context import get_current_orchestrator, get_current_session_key
from butler.tools.file_io_ops import (
    maybe_format_after_edit_safe,
    record_edit_path_safe,
    record_read_path_safe,
    tool_json_loud,
    verify_hashline_anchors_safe,
)
from butler.tools.path_safety import check_tool_path, tool_safe_root

MAX_READ_FILE_BYTES = 1024 * 1024
MAX_READ_FILE_LINES = 1000


def _raw_tool_path(path: str | os.PathLike[str], root: Path) -> Path:
    raw_path = Path(str(path or ".")).expanduser()
    if not raw_path.is_absolute():
        raw_path = root / raw_path
    return raw_path


def _read_limited_fd(fd: int) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(65536, MAX_READ_FILE_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_READ_FILE_BYTES:
            return b"", f"File too large: maximum is {MAX_READ_FILE_BYTES} bytes"
    return b"".join(chunks), ""


def _write_all_fd(fd: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(data):
        n = os.write(fd, view[written:])
        if n == 0:
            raise OSError("short write while writing tool file")
        written += n


def _validate_existing_target_unchanged(
    dir_fd: int,
    name: str,
    expected_stat: os.stat_result,
) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return "Access denied: file changed during validation"
    except OSError as exc:
        return _format_open_error(exc)
    try:
        current_stat = os.fstat(fd)
        if not stat_module.S_ISREG(current_stat.st_mode):
            return "Access denied: only regular files can be written"
        if current_stat.st_nlink > 1:
            return "Access denied: hardlinked files are not allowed"
        if (current_stat.st_dev, current_stat.st_ino) != (
            expected_stat.st_dev,
            expected_stat.st_ino,
        ):
            return "Access denied: file changed during validation"
        return ""
    finally:
        os.close(fd)


def _validate_regular_file_stat(
    stat_result: os.stat_result,
    expected_stat: os.stat_result,
) -> str:
    if (stat_result.st_dev, stat_result.st_ino) != (
        expected_stat.st_dev,
        expected_stat.st_ino,
    ):
        return "Access denied: file changed during validation"
    if not stat_module.S_ISREG(stat_result.st_mode):
        return "Access denied: only regular files can be read"
    if stat_result.st_nlink > 1:
        return "Access denied: hardlinked files are not allowed"
    if stat_result.st_size > MAX_READ_FILE_BYTES:
        return f"File too large: maximum is {MAX_READ_FILE_BYTES} bytes"
    return ""


def _symlink_component_error(
    raw_path: Path,
    root: Path,
    *,
    include_final: bool,
) -> str:
    try:
        relative = raw_path.relative_to(root)
    except ValueError:
        return ""
    current = root
    parts = relative.parts if include_final else relative.parts[:-1]
    for part in parts:
        current = current / part
        try:
            if current.is_symlink():
                return "Access denied: symlinks are not allowed"
        except OSError:
            return "Access denied: path could not be validated"
    return ""


def _format_open_error(exc: OSError) -> str:
    if "Too many levels of symbolic links" in str(exc):
        return "Access denied: symlinks are not allowed"
    return str(exc)


def _read_regular_file_bytes(
    path: str | os.PathLike[str],
    *,
    for_write: bool = False,
) -> tuple[bytes, Path | None, os.stat_result | None, str]:
    root = tool_safe_root()
    safety = check_tool_path(path, for_write=for_write)
    if not safety.allowed:
        return b"", None, None, safety.error
    p = safety.path
    if not p.exists():
        return b"", p, None, f"File not found: {path}"

    raw_path = _raw_tool_path(path, root)
    symlink_error = _symlink_component_error(raw_path, root, include_final=True)
    if symlink_error:
        return b"", p, None, symlink_error

    expected_stat = p.stat()
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(raw_path, flags)
    except OSError as exc:
        return b"", p, None, _format_open_error(exc)

    try:
        stat_result = os.fstat(fd)
        validation_error = _validate_regular_file_stat(stat_result, expected_stat)
        if validation_error:
            return b"", p, None, validation_error
        data, read_error = _read_limited_fd(fd)
        if read_error:
            return b"", p, None, read_error
        return data, p, stat_result, ""
    finally:
        os.close(fd)


def _atomic_write_text(
    path: str | os.PathLike[str],
    content: str,
    *,
    expected_stat: os.stat_result | None = None,
) -> tuple[Path | None, str]:
    root = tool_safe_root()
    safety = check_tool_path(path, for_write=True)
    if not safety.allowed:
        return None, safety.error
    p = safety.path
    raw_path = _raw_tool_path(path, root)
    symlink_error = _symlink_component_error(raw_path, root, include_final=raw_path.exists())
    if symlink_error:
        return None, symlink_error

    p.parent.mkdir(parents=True, exist_ok=True)
    raw_parent = raw_path.parent
    symlink_error = _symlink_component_error(raw_parent, root, include_final=True)
    if symlink_error:
        return None, symlink_error
    try:
        parent_stat = raw_parent.stat()
    except OSError as exc:
        return None, str(exc)
    if not stat_module.S_ISDIR(parent_stat.st_mode):
        return None, "Access denied: parent path is not a directory"

    if raw_path.exists():
        try:
            current_stat = raw_path.lstat()
        except OSError as exc:
            return None, str(exc)
        if stat_module.S_ISLNK(current_stat.st_mode):
            return None, "Access denied: symlinks are not allowed"
        if not stat_module.S_ISREG(current_stat.st_mode):
            return None, "Access denied: only regular files can be written"
        if current_stat.st_nlink > 1:
            return None, "Access denied: hardlinked files are not allowed"
        if expected_stat is None:
            expected_stat = current_stat
        elif (
            current_stat.st_dev,
            current_stat.st_ino,
        ) != (expected_stat.st_dev, expected_stat.st_ino):
            return None, "Access denied: file changed during validation"

    parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        dir_fd = os.open(raw_parent, parent_flags)
    except OSError as exc:
        return None, _format_open_error(exc)

    temp_name = f".{raw_path.name}.butler-tmp-{os.getpid()}-{time.monotonic_ns()}"
    temp_created = False
    try:
        dir_stat = os.fstat(dir_fd)
        if (dir_stat.st_dev, dir_stat.st_ino) != (parent_stat.st_dev, parent_stat.st_ino):
            return None, "Access denied: parent directory changed during validation"
        fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=dir_fd,
        )
        temp_created = True
        try:
            data = content.encode("utf-8")
            _write_all_fd(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        if expected_stat is not None:
            current_error = _validate_existing_target_unchanged(dir_fd, raw_path.name, expected_stat)
            if current_error:
                return None, current_error
        os.replace(temp_name, raw_path.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        temp_created = False
        return p, ""
    except OSError as exc:
        return None, str(exc)
    finally:
        if temp_created:
            try:
                os.unlink(temp_name, dir_fd=dir_fd)
            except OSError:
                pass
        os.close(dir_fd)


def _tool_read_file(path: str, offset: int = 1, limit: int = 500, **_: Any) -> str:
    def _run() -> str:
        try:
            off = int(offset)
            lim = int(limit)
        except (TypeError, ValueError):
            return json.dumps({"error": "read_file offset and limit must be integers"})
        if lim < 1 or lim > MAX_READ_FILE_LINES:
            return json.dumps({
                "error": f"read_file limit exceeds maximum ({MAX_READ_FILE_LINES} lines)"
            })
        if off < 1:
            return json.dumps({"error": "read_file offset must be >= 1"})

        data, _p, _stat, error = _read_regular_file_bytes(path)
        if error:
            return json.dumps({"error": error})
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if (
            off == 1
            and len(lines) > read_summary_threshold_lines()
            and lim >= 100
        ):
            summary = build_large_file_summary(str(path), lines)
            return str(format_summary_message(summary))
        start = off - 1
        end = start + lim
        selected = lines[start:end]
        if _p is not None:
            body = format_read_output(_p, selected, start + 1)
        else:
            if hashline_read_enabled():
                body = "\n".join(
                    format_hash_line(start + i + 1, line)
                    for i, line in enumerate(selected)
                )
            else:
                body = "\n".join(
                    f"{i + start + 1:6}|{line}" for i, line in enumerate(selected)
                )
        if _p is not None and _stat is not None:
            record_read_state(
                _p,
                _stat,
                data,
                session_key=str(get_current_session_key() or "").strip() or None,
            )
            orch = get_current_orchestrator()
            workspace_root = None
            if orch is not None:
                pm = getattr(orch, "project_manager", None)
                proj = pm.get_current() if pm is not None else None
                if proj is not None:
                    workspace_root = Path(proj.workspace)
            record_read_path_safe(_p, workspace_root=workspace_root)
        return str(body)

    return str(tool_json_loud(_run))


def _tool_write_file(path: str, content: str, **_: Any) -> str:
    def _run() -> str:
        guard = require_read_before_edit(path, for_write=True)
        if guard:
            return json.dumps(guard, ensure_ascii=False)
        p, error = _atomic_write_text(path, content)
        if error:
            return json.dumps({"error": error})
        record_edit_path_safe(p)
        payload: dict[str, Any] = {"success": True, "path": str(p), "bytes": len(content.encode("utf-8"))}
        fmt = maybe_format_after_edit_safe(p)
        if fmt:
            payload["post_edit_format"] = fmt
        return json.dumps(payload)

    return str(tool_json_loud(_run))


def _tool_delete_file(path: str, **_: Any) -> str:
    def _run() -> str:
        _data, p, stat_result, error = _read_regular_file_bytes(path, for_write=True)
        if error:
            return json.dumps({"error": error})
        if p is None or stat_result is None:
            return json.dumps({"error": f"File not found: {path}"})
        if not stat_module.S_ISREG(stat_result.st_mode):
            return json.dumps({"error": "Only regular files can be deleted (not directories)"})

        root = tool_safe_root()
        raw_path = _raw_tool_path(path, root)
        symlink_error = _symlink_component_error(raw_path, root, include_final=True)
        if symlink_error:
            return json.dumps({"error": symlink_error})

        try:
            os.unlink(raw_path)
        except OSError as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({"success": True, "path": str(p), "action": "deleted"})

    return str(tool_json_loud(_run))


def _tool_patch(path: str, old_string: str, new_string: str, **_: Any) -> str:
    def _run() -> str:
        guard = require_read_before_edit(path, for_write=True)
        if guard:
            return json.dumps(guard, ensure_ascii=False)
        data, _p, expected_stat, error = _read_regular_file_bytes(path, for_write=True)
        if error:
            return json.dumps({"error": error})
        if _p is not None:
            mismatch = verify_hashline_anchors_safe(_p, old_string)
            if mismatch:
                return json.dumps(mismatch, ensure_ascii=False)
        text = data.decode("utf-8", errors="replace")
        needle = old_string
        replacement = new_string
        count = text.count(needle)
        fuzzy = False
        if count == 0:
            norm_text = normalize_quotes(text)
            norm_old = normalize_quotes(needle)
            count = norm_text.count(norm_old)
            if count > 0:
                text = norm_text
                needle = norm_old
                replacement = normalize_quotes(replacement)
                fuzzy = True
        if count == 0:
            return json.dumps({
                "error": "old_string not found in file",
                "code": "PATCH_OLD_STRING_NOT_FOUND",
                "hint": (
                    "read_file the path again and copy old_string verbatim from the file "
                    "(indentation, quotes, and trailing newlines must match)."
                ),
            }, ensure_ascii=False)
        if count > 1:
            matches: list[dict[str, Any]] = []
            start = 0
            while len(matches) < 3:
                idx = text.find(needle, start)
                if idx < 0:
                    break
                line_no = text.count("\n", 0, idx) + 1
                line_start = text.rfind("\n", 0, idx) + 1
                line_end = text.find("\n", idx)
                if line_end < 0:
                    line_end = len(text)
                excerpt = text[line_start:line_end].strip()
                if len(excerpt) > 120:
                    excerpt = excerpt[:117] + "..."
                matches.append({"line": line_no, "excerpt": excerpt})
                start = idx + len(needle)
            return json.dumps({
                "error": f"old_string found {count} times; must be unique",
                "match_count": count,
                "matches": matches,
            })
        new_text = text.replace(needle, replacement, 1)
        _written_path, write_error = _atomic_write_text(path, new_text, expected_stat=expected_stat)
        if write_error:
            return json.dumps({"error": write_error})
        record_edit_path_safe(_written_path)
        payload: dict[str, Any] = {"success": True, "replacements": 1}
        if _written_path is not None:
            payload["path"] = str(_written_path)
        if fuzzy:
            payload["fuzzy_quotes"] = True
        if _written_path is not None:
            fmt = maybe_format_after_edit_safe(_written_path)
            if fmt:
                payload["post_edit_format"] = fmt
        return json.dumps(payload)

    return str(tool_json_loud(_run))
