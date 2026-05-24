"""Butler Tool Registry — manages tool schemas and dispatch.

Independent from Hermes tool system. Tools register here and
the AgentLoop dispatches through this registry.
"""

from __future__ import annotations

import json
import logging
import os
import stat as stat_module
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)
MAX_READ_FILE_BYTES = 1024 * 1024
MAX_READ_FILE_LINES = 1000
MAX_TERMINAL_TIMEOUT_SECONDS = 120
MAX_TERMINAL_OUTPUT_CHARS = 50000
_TOOL_AUDIT_EVENTS: deque[dict[str, Any]] = deque(maxlen=200)
_TOOL_AUDIT_EVENTS_BY_SESSION: dict[str, deque[dict[str, Any]]] = {}
_TOOL_AUDIT_LOCK = threading.RLock()


class ToolEntry:
    __slots__ = ("name", "description", "schema", "handler", "toolset")

    def __init__(
        self,
        name: str,
        description: str,
        schema: dict,
        handler: Callable,
        toolset: str = "default",
    ):
        self.name = name
        self.description = description
        self.schema = schema
        self.handler = handler
        self.toolset = toolset


_REGISTRY: Dict[str, ToolEntry] = {}


def register(
    name: str,
    description: str,
    schema: dict,
    handler: Callable,
    toolset: str = "default",
) -> None:
    _REGISTRY[name] = ToolEntry(name, description, schema, handler, toolset)


def get_tool_definitions() -> List[dict]:
    """Return OpenAI function-calling format tool definitions."""
    _ensure_builtins()
    result = []
    for entry in _REGISTRY.values():
        result.append({
            "type": "function",
            "function": {
                "name": entry.name,
                "description": entry.description,
                "parameters": entry.schema,
            },
        })
    return result


def dispatch_tool(name: str, args: dict) -> str:
    """Dispatch a tool call by name. Returns result as string."""
    _ensure_builtins()
    entry = _REGISTRY.get(name)
    if entry is None:
        return _finalize_tool_result(
            name,
            args,
            {"error": f"Unknown tool: {name}"},
            started_at=time.monotonic(),
        )

    from butler.plan_mode import check_plan_mode_block

    plan_block = check_plan_mode_block(name, args)
    if plan_block:
        return _finalize_tool_result(
            name,
            args,
            {"error": plan_block, "code": "PLAN_MODE_BLOCKED"},
            started_at=time.monotonic(),
        )

    started_at = time.monotonic()
    try:
        from butler.hooks.runner import run_pre_tool_hooks

        pre_block = run_pre_tool_hooks(name, args)
        if pre_block:
            return _finalize_tool_result(
                name,
                args,
                {"error": pre_block, "code": "HOOK_BLOCKED"},
                started_at=started_at,
            )
    except Exception as exc:
        logger.debug("Pre tool hooks skipped: %s", exc)

    try:
        result = entry.handler(**args)
        return _apply_post_tool_hooks(
            name,
            args,
            _finalize_tool_result(name, args, result, started_at=started_at),
        )
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        err_result = _finalize_tool_result(
            name,
            args,
            {"error": f"Tool '{name}' failed: {exc}"},
            started_at=started_at,
        )
        return _apply_post_tool_hooks(name, args, err_result, failed=True)


def _apply_post_tool_hooks(
    name: str,
    args: dict,
    finalized: str,
    *,
    failed: bool = False,
) -> str:
    try:
        payload = json.loads(finalized)
        if not failed and isinstance(payload, dict):
            failed = (
                payload.get("ok") is False
                or "error" in payload
                or payload.get("success") is False
            )
    except (TypeError, ValueError, json.JSONDecodeError):
        if not failed:
            failed = '"error"' in finalized
    try:
        from butler.hooks.runner import run_post_tool_hooks

        return run_post_tool_hooks(name, args, finalized, failed=failed)
    except Exception as exc:
        logger.debug("Post tool hooks skipped: %s", exc)
        return finalized


def finalize_tool_result(
    name: str,
    args: dict,
    result: Any,
    *,
    started_at: float | None = None,
) -> str:
    """Apply Butler's tool result envelope and audit record to fallback paths."""
    return _finalize_tool_result(
        name,
        args,
        result,
        started_at=started_at if started_at is not None else time.monotonic(),
    )


def get_tool_audit_events(
    limit: int | None = None,
    *,
    session_key: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent tool audit events with redacted arguments."""
    with _TOOL_AUDIT_LOCK:
        if session_key is None:
            events = list(_TOOL_AUDIT_EVENTS)
        else:
            events = list(_TOOL_AUDIT_EVENTS_BY_SESSION.get(session_key, ()))
    if limit is not None:
        events = events[-max(0, int(limit)):]
    return [dict(event) for event in events]


def reset_tool_audit_events(session_key: str | None = None) -> None:
    """Clear in-memory tool audit events. Intended for tests and diagnostics reset."""
    with _TOOL_AUDIT_LOCK:
        if session_key is None:
            _TOOL_AUDIT_EVENTS.clear()
            _TOOL_AUDIT_EVENTS_BY_SESSION.clear()
            return
        _TOOL_AUDIT_EVENTS_BY_SESSION.pop(session_key, None)
        retained = [
            event for event in _TOOL_AUDIT_EVENTS
            if event.get("session_key") != session_key
        ]
        _TOOL_AUDIT_EVENTS.clear()
        _TOOL_AUDIT_EVENTS.extend(retained[-_TOOL_AUDIT_EVENTS.maxlen:])


def pop_last_tool_audit_for_tool(name: str) -> None:
    """Remove the latest audit event for a tool when replacing it with guardrail halt."""
    with _TOOL_AUDIT_LOCK:
        if not _TOOL_AUDIT_EVENTS or _TOOL_AUDIT_EVENTS[-1].get("tool") != name:
            return
        last = _TOOL_AUDIT_EVENTS.pop()
        session_key = str(last.get("session_key") or "")
        bucket = _TOOL_AUDIT_EVENTS_BY_SESSION.get(session_key)
        if bucket and bucket[-1].get("tool") == name:
            bucket.pop()


def _finalize_tool_result(
    name: str,
    args: dict,
    result: Any,
    *,
    started_at: float,
) -> str:
    if isinstance(result, str):
        payload = _parse_json_object(result)
        if payload is None:
            ok = True
            code = "TOOL_OK"
            _record_tool_audit(name, args, ok=ok, code=code, started_at=started_at)
            return result
    elif isinstance(result, dict):
        payload = dict(result)
    else:
        payload = result

    if isinstance(payload, dict):
        ok = _tool_result_ok(payload)
        code = _tool_result_code(name, payload, ok=ok)
        if not ok:
            payload.setdefault("ok", False)
            payload.setdefault("tool", name)
            payload.setdefault("code", code)
        _record_tool_audit(name, args, ok=ok, code=code, started_at=started_at)
        return json.dumps(payload, ensure_ascii=False, default=str)

    _record_tool_audit(name, args, ok=True, code="TOOL_OK", started_at=started_at)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _tool_result_ok(payload: dict[str, Any]) -> bool:
    if payload.get("ok") is False:
        return False
    if "error" in payload:
        return False
    if payload.get("success") is False:
        return False
    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return False
    return True


def _tool_result_code(name: str, payload: dict[str, Any], *, ok: bool) -> str:
    if ok:
        return "TOOL_OK"
    guardrail = payload.get("guardrail")
    if isinstance(guardrail, dict):
        action = guardrail.get("action")
        if action == "halt":
            return "TOOL_GUARDRAIL_HALT"
        if action == "block":
            return "TOOL_GUARDRAIL_BLOCKED"
    if payload.get("code"):
        return str(payload["code"])
    error = str(payload.get("error") or "")
    if error == "interrupted":
        return "TOOL_INTERRUPTED"
    if isinstance(payload.get("exit_code"), int) and payload["exit_code"] != 0:
        return "TOOL_EXIT_NONZERO"
    if name not in _REGISTRY:
        return "TOOL_NOT_FOUND"
    lowered = error.lower()
    if (
        "access denied" in lowered
        or "outside workspace" in lowered
        or "sensitive" in lowered
        or "symlink" in lowered
        or "hardlinked" in lowered
    ):
        return "TOOL_SECURITY_DENIED"
    if lowered.startswith("file not found") or lowered.startswith("unknown tool"):
        return "TOOL_NOT_FOUND"
    if "timeout" in lowered or "timed out" in lowered:
        return "TOOL_TIMEOUT"
    if "too large" in lowered or "limit" in lowered:
        return "TOOL_RESOURCE_LIMIT"
    return "TOOL_ERROR"


def _record_tool_audit(
    name: str,
    args: dict,
    *,
    ok: bool,
    code: str,
    started_at: float,
) -> None:
    try:
        from butler.execution_context import get_audit_session_key

        session_key = get_audit_session_key()
    except Exception:
        session_key = "unscoped"
    event = {
        "tool": name,
        "ok": ok,
        "code": code,
        "session_key": session_key or "",
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 2),
        "arg_keys": sorted(str(key) for key in (args or {}).keys()),
    }
    with _TOOL_AUDIT_LOCK:
        _TOOL_AUDIT_EVENTS.append(event)
        bucket = _TOOL_AUDIT_EVENTS_BY_SESSION.setdefault(
            event["session_key"],
            deque(maxlen=200),
        )
        bucket.append(event)

    try:
        from butler.tools.audit_persist import persist_tool_audit_event

        persist_tool_audit_event(event)
    except Exception as exc:
        logger.debug("Tool audit persist skipped: %s", exc)


_builtins_loaded = False


def _ensure_builtins() -> None:
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    _register_builtin_tools()


def _register_builtin_tools() -> None:
    """Register Butler's core development tools."""

    # ── read_file ─────────────────────────────────────────────
    register(
        name="read_file",
        description="Read content from a file. Returns the file content as text.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
                "offset": {"type": "integer", "description": "Line number to start from (1-indexed)", "default": 1},
                "limit": {
                    "type": "integer",
                    "description": f"Max lines to read (1-{MAX_READ_FILE_LINES})",
                    "default": 500,
                    "minimum": 1,
                    "maximum": MAX_READ_FILE_LINES,
                },
            },
            "required": ["path"],
        },
        handler=_tool_read_file,
        toolset="file",
    )

    # ── write_file ────────────────────────────────────────────
    register(
        name="write_file",
        description="Write content to a file. Creates the file if it doesn't exist.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        handler=_tool_write_file,
        toolset="file",
    )

    # ── patch ─────────────────────────────────────────────────
    register(
        name="patch",
        description="Replace a specific string in a file. The old_string must match exactly.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "old_string": {"type": "string", "description": "Exact text to find"},
                "new_string": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        handler=_tool_patch,
        toolset="file",
    )

    register(
        name="delete_file",
        description=(
            "Delete a regular file under the project workspace. "
            "Prefer this over terminal rm. Does not remove directories."
        ),
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to delete"},
            },
            "required": ["path"],
        },
        handler=_tool_delete_file,
        toolset="file",
    )

    # ── terminal ──────────────────────────────────────────────
    register(
        name="terminal",
        description="Execute a restricted argv command when BUTLER_ENABLE_TERMINAL=1.",
        schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in seconds (1-{MAX_TERMINAL_TIMEOUT_SECONDS})",
                    "default": 30,
                    "minimum": 1,
                    "maximum": MAX_TERMINAL_TIMEOUT_SECONDS,
                },
                "workdir": {"type": "string", "description": "Working directory"},
            },
            "required": ["command"],
        },
        handler=_tool_terminal,
        toolset="shell",
    )

    # ── search_files ──────────────────────────────────────────
    register(
        name="search_files",
        description="Search for a pattern in files using ripgrep.",
        schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex)"},
                "path": {"type": "string", "description": "Directory or file to search in", "default": "."},
                "include": {"type": "string", "description": "Glob pattern to filter files"},
            },
            "required": ["pattern"],
        },
        handler=_tool_search_files,
        toolset="search",
    )

    # ── list_directory ────────────────────────────────────────
    register(
        name="list_directory",
        description="List files and directories in a given path.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
            },
        },
        handler=_tool_list_directory,
        toolset="file",
    )

    # ── delegate_task (Butler-native) ─────────────────────────
    register(
        name="skills_list",
        description="List available skills (metadata only). Use skill_view to load full content.",
        schema={"type": "object", "properties": {}},
        handler=_tool_skills_list,
        toolset="skills",
    )

    register(
        name="skill_view",
        description="Load full content of a skill by name.",
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name (kebab-case)"},
            },
            "required": ["name"],
        },
        handler=_tool_skill_view,
        toolset="skills",
    )

    register(
        name="run_workflow",
        description=(
            "Run a named project workflow (DAG of dev/content/review agents). "
            "Workflows are declared in project.yaml or .butler/workflows/."
        ),
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workflow name (e.g. novel-factory)"},
                "hint": {
                    "type": "string",
                    "description": "Optional user goal appended to each step",
                    "default": "",
                },
            },
            "required": ["name"],
        },
        handler=_tool_run_workflow,
        toolset="delegation",
    )

    register(
        name="delegate_task",
        description="Delegate a task to a project-level agent (dev/content/review). Butler orchestrates the sub-agent.",
        schema={
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "Agent role: 'dev', 'content', or 'review'",
                    "enum": ["dev", "content", "review"],
                },
                "task": {"type": "string", "description": "Task description"},
                "context": {"type": "string", "description": "Additional context for the agent"},
            },
            "required": ["role", "task"],
        },
        handler=_tool_delegate_task,
        toolset="delegation",
    )

    from butler.tools.memory_tools import register_memory_tools

    register_memory_tools(register)

    from butler.tools.git_tools import register_git_tools

    register_git_tools(register)

    from butler.tools.runtime_tools import register_runtime_tools

    register_runtime_tools(register)

    from butler.tools.download_tools import register_download_tools

    register_download_tools(register)


# ── Tool Implementations ─────────────────────────────────────

def _tool_read_file(path: str, offset: int = 1, limit: int = 500, **_) -> str:
    try:
        try:
            offset = int(offset)
            limit = int(limit)
        except (TypeError, ValueError):
            return json.dumps({"error": "read_file offset and limit must be integers"})
        if limit < 1 or limit > MAX_READ_FILE_LINES:
            return json.dumps({
                "error": f"read_file limit exceeds maximum ({MAX_READ_FILE_LINES} lines)"
            })
        if offset < 1:
            return json.dumps({"error": "read_file offset must be >= 1"})

        data, _p, _stat, error = _read_regular_file_bytes(path)
        if error:
            return json.dumps({"error": error})
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        start = offset - 1
        end = start + limit
        selected = lines[start:end]
        numbered = [f"{i + start + 1:6}|{line}" for i, line in enumerate(selected)]
        return "\n".join(numbered)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _raw_tool_path(path: str | os.PathLike[str], root: Path) -> Path:
    raw_path = Path(str(path or ".")).expanduser()
    if not raw_path.is_absolute():
        raw_path = root / raw_path
    return raw_path


def _read_regular_file_bytes(
    path: str | os.PathLike[str],
    *,
    for_write: bool = False,
) -> tuple[bytes, Path | None, os.stat_result | None, str]:
    from butler.tools.path_safety import check_tool_path, tool_safe_root

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
    from butler.tools.path_safety import check_tool_path, tool_safe_root

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


def _tool_write_file(path: str, content: str, **_) -> str:
    try:
        p, error = _atomic_write_text(path, content)
        if error:
            return json.dumps({"error": error})
        return json.dumps({"success": True, "path": str(p), "bytes": len(content.encode("utf-8"))})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_delete_file(path: str, **_) -> str:
    """Delete one regular file inside the tool-safe workspace."""
    try:
        _data, p, stat_result, error = _read_regular_file_bytes(path, for_write=True)
        if error:
            return json.dumps({"error": error})
        if p is None or stat_result is None:
            return json.dumps({"error": f"File not found: {path}"})
        if not stat_module.S_ISREG(stat_result.st_mode):
            return json.dumps({"error": "Only regular files can be deleted (not directories)"})

        from butler.tools.path_safety import tool_safe_root

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
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_patch(path: str, old_string: str, new_string: str, **_) -> str:
    try:
        data, _p, expected_stat, error = _read_regular_file_bytes(path, for_write=True)
        if error:
            return json.dumps({"error": error})
        text = data.decode("utf-8", errors="replace")
        count = text.count(old_string)
        if count == 0:
            return json.dumps({"error": "old_string not found in file"})
        if count > 1:
            matches: list[dict[str, Any]] = []
            start = 0
            while len(matches) < 3:
                idx = text.find(old_string, start)
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
                start = idx + len(old_string)
            return json.dumps({
                "error": f"old_string found {count} times; must be unique",
                "match_count": count,
                "matches": matches,
            })
        new_text = text.replace(old_string, new_string, 1)
        _written_path, write_error = _atomic_write_text(path, new_text, expected_stat=expected_stat)
        if write_error:
            return json.dumps({"error": write_error})
        return json.dumps({"success": True, "replacements": 1})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_terminal(command: str, timeout: int = 30, workdir: str = None, **_) -> str:
    import threading
    from butler.tools.interrupt import is_interrupted
    from butler.tools.path_safety import (
        check_tool_path,
        default_tool_workdir,
        prepare_shell_command,
        safe_subprocess_env,
    )

    if os.getenv("BUTLER_ENABLE_TERMINAL", "").strip() != "1":
        return json.dumps({
            "error": "Terminal tool is disabled by default. Set BUTLER_ENABLE_TERMINAL=1 to enable restricted commands."
        })

    thread_id = threading.get_ident()
    proc: subprocess.Popen[str] | None = None
    interrupted = False
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        return json.dumps({"error": "Terminal timeout must be an integer number of seconds"})
    if timeout < 1 or timeout > MAX_TERMINAL_TIMEOUT_SECONDS:
        return json.dumps({
            "error": f"Terminal timeout must be between 1 and {MAX_TERMINAL_TIMEOUT_SECONDS} seconds"
        })
    command_safety = prepare_shell_command(command)
    if not command_safety.allowed:
        return json.dumps({"error": command_safety.error})

    if workdir:
        safety = check_tool_path(workdir)
    else:
        safety = default_tool_workdir()
    if not safety.allowed:
        return json.dumps({"error": safety.error})
    if not safety.path.is_dir():
        return json.dumps({"error": f"Not a directory: {workdir or safety.path}"})
    resolved_workdir = str(safety.path)

    def _watch() -> None:
        nonlocal interrupted
        while proc is not None and proc.poll() is None:
            if is_interrupted(thread_id):
                interrupted = True
                proc.kill()
                return
            time.sleep(0.2)

    try:
        proc = subprocess.Popen(
            command_safety.argv,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=resolved_workdir,
            env=safe_subprocess_env(),
        )
        watcher = threading.Thread(target=_watch, daemon=True)
        watcher.start()
        try:
            stdout, stderr, truncated = _communicate_limited(
                proc,
                timeout=timeout,
                max_output_chars=MAX_TERMINAL_OUTPUT_CHARS,
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=1)
            finally:
                _close_pipe(proc.stdout)
                _close_pipe(proc.stderr)
            return json.dumps({"error": f"Command timed out after {timeout}s"})
        if interrupted:
            return json.dumps({"error": "interrupted", "output": ""})
        output = stdout or ""
        if stderr:
            output += "\n[stderr]\n" + stderr
        if truncated or len(output) > MAX_TERMINAL_OUTPUT_CHARS:
            output = output[:MAX_TERMINAL_OUTPUT_CHARS] + "\n... (truncated)"
        return json.dumps({
            "exit_code": proc.returncode,
            "output": output,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _communicate_limited(
    proc: subprocess.Popen,
    *,
    timeout: int,
    max_output_chars: int,
) -> tuple[str, str, bool]:
    """Read process pipes incrementally so tool output cannot exhaust memory."""
    if not (_is_selectable_pipe(proc.stdout) and _is_selectable_pipe(proc.stderr)):
        stdout, stderr = proc.communicate(timeout=timeout)
        return str(stdout or ""), str(stderr or ""), (
            len(str(stdout or "")) + len(str(stderr or "")) > max_output_chars
        )

    import selectors

    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
    selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
    stdout_parts: list[bytes] = []
    stderr_parts: list[bytes] = []
    total = 0
    truncated = False
    deadline = time.monotonic() + timeout

    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(proc.args, timeout)
            events = selector.select(timeout=min(0.2, remaining))
            if not events:
                if proc.poll() is not None:
                    # Give pipes one final chance to report EOF.
                    continue
                continue
            for key, _mask in events:
                pipe = key.fileobj
                chunk = pipe.read1(8192) if hasattr(pipe, "read1") else pipe.read(8192)
                if not chunk:
                    selector.unregister(pipe)
                    continue
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8", errors="replace")
                room = max(0, max_output_chars - total)
                if room:
                    kept = chunk[:room]
                    if key.data == "stdout":
                        stdout_parts.append(kept)
                    else:
                        stderr_parts.append(kept)
                    total += len(kept)
                if len(chunk) > room:
                    truncated = True
        proc.wait(timeout=max(0, deadline - time.monotonic()))
    finally:
        selector.close()

    stdout = b"".join(stdout_parts).decode("utf-8", errors="replace")
    stderr = b"".join(stderr_parts).decode("utf-8", errors="replace")
    return stdout, stderr, truncated


def _is_selectable_pipe(pipe: Any) -> bool:
    try:
        return isinstance(pipe.fileno(), int)
    except Exception:
        return False


def _close_pipe(pipe: Any) -> None:
    try:
        if pipe is not None:
            pipe.close()
    except Exception:
        return


def _tool_search_files(pattern: str, path: str = ".", include: str = None, **_) -> str:
    from butler.tools.path_safety import check_tool_path, safe_subprocess_env

    safety = check_tool_path(path)
    if not safety.allowed:
        return json.dumps({"error": safety.error})
    cmd = ["rg", "--no-config", "--json", "-m", "20"]
    if include:
        cmd.extend(["--glob", include])
    cmd.extend(["--", pattern, str(safety.path)])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            env=safe_subprocess_env(),
        )
        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("type") == "match":
                    data = obj["data"]
                    path_text = data["path"]["text"]
                    match_safety = check_tool_path(path_text)
                    if not match_safety.allowed:
                        continue
                    matches.append({
                        "path": str(match_safety.path),
                        "line": data["line_number"],
                        "text": data["lines"]["text"].rstrip(),
                    })
            except (json.JSONDecodeError, KeyError):
                continue
        return json.dumps({"matches": matches[:50], "total": len(matches)})
    except FileNotFoundError:
        return json.dumps({"error": "ripgrep (rg) not installed"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_list_directory(path: str = ".", **_) -> str:
    from butler.tools.path_safety import check_tool_path

    safety = check_tool_path(path)
    if not safety.allowed:
        return json.dumps({"error": safety.error})
    p = safety.path
    if not p.is_dir():
        return json.dumps({"error": f"Not a directory: {path}"})
    try:
        entries = []
        for item in sorted(p.iterdir()):
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
        return json.dumps({"path": str(p), "entries": entries[:200]})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_skills_list(**_) -> str:
    try:
        orch = _orchestrator_for_tool(channel="tool")
        mgr = orch._skill_manager
        if mgr is None:
            return json.dumps({"skills": []})
        skills = [
            {"name": s.get("name"), "description": s.get("description", "")[:200]}
            for s in mgr.list_skills()
        ]
        return json.dumps({"skills": skills}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_skill_view(name: str, **_) -> str:
    try:
        orch = _orchestrator_for_tool(channel="tool")
        mgr = orch._skill_manager
        if mgr is None:
            return json.dumps({"error": "Skill manager unavailable"})
        skill = mgr.get_skill(name)
        if not skill:
            return json.dumps({"error": f"Skill not found: {name}"})
        return json.dumps({
            "name": skill.get("name"),
            "description": skill.get("description"),
            "content": skill.get("content", ""),
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_run_workflow(name: str, hint: str = "", **_) -> str:
    """Execute a project workflow DAG via TaskOrchestrator."""
    try:
        from butler.execution_context import get_current_session_key
        from butler.gateway.outbound_bridge import get_gateway_bridge_optional
        from butler.workflows.runner import run_workflow_for_project

        bridge = get_gateway_bridge_optional()
        if bridge is not None:
            bridge.notify_workflow_step(name, "start", step_index=0, step_total=0)

        orch = _orchestrator_for_tool(channel="cli")
        project = orch.project_manager.get_current()
        if project is None:
            return json.dumps({"error": "No active project; switch project first"}, ensure_ascii=False)
        session_key = str(get_current_session_key() or "").strip()
        text = run_workflow_for_project(
            project,
            name,
            user_hint=hint or "",
            session_key=session_key,
            orchestrator=orch,
        )
        return json.dumps({"success": True, "summary": text}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _finalize_delegate_failure(
    *,
    role: str,
    task: str,
    exc: Exception,
    task_id: str = "",
    session_key: str = "",
) -> str:
    from butler.report import AgentReport, cache_report
    from butler.runtime.task_store import complete_task

    role_label = _delegate_role_label(role)
    headline = f"{role_label}委派失败"
    summary = str(exc)[:2000]
    if task_id:
        complete_task(
            task_id,
            success=False,
            report_headline=headline,
            summary=summary,
        )
    report = AgentReport(
        headline=headline,
        summary=summary,
        success=False,
        task_preview=(task or "")[:200],
        task_id=task_id,
        issues=[summary[:500]],
    )
    cache_report(report, session_key=session_key or "default")
    payload: dict[str, Any] = {
        "success": False,
        "error": f"Delegation failed: {exc}",
        "headline": headline,
    }
    if task_id:
        payload["task_id"] = task_id
    return json.dumps(payload, ensure_ascii=False)


def _tool_delegate_task(role: str, task: str, context: str = "", depth: int = 0, **_) -> str:
    """Delegate to a project-level agent through Butler's orchestrator."""
    task_id = ""
    session_key = ""
    try:
        from butler.delegate_policy import DELEGATE_BLOCKED_TOOLS, MAX_DELEGATE_DEPTH
        from butler.gateway.outbound_bridge import get_gateway_bridge_optional

        bridge = get_gateway_bridge_optional()
        if bridge is not None:
            bridge.notify_delegate_start(role, preview=task[:80])

        if depth >= MAX_DELEGATE_DEPTH:
            return json.dumps({"error": f"Maximum delegation depth ({MAX_DELEGATE_DEPTH}) exceeded"})

        orch = _orchestrator_for_tool(channel="cli")
        from butler.tools.project_tools import get_tool_definitions_for_project

        project = orch.project_manager.get_current()
        tools = get_tool_definitions_for_project(project, role=role)

        delegated_tools = [
            t for t in tools
            if t["function"]["name"] not in DELEGATE_BLOCKED_TOOLS
        ]

        from butler.core.delegate_context import child_callbacks, get_parent_callbacks

        parent_cb = get_parent_callbacks()
        agent = orch.create_project_agent_loop(
            role=role,
            tools=delegated_tools,
            tool_dispatcher=lambda name, args: _safe_dispatch(name, args, depth + 1),
            callbacks=child_callbacks(parent_cb),
        )
        agent.reset()

        raw_user_msg = _project_agent_raw_message(task=task, context=context)
        user_msg = _inject_project_agent_skills(orch, raw_user_msg)

        from butler.session_lifecycle import attach_turn_memory_prefetch, sync_turn_memory
        from butler.execution_context import get_current_session_key, use_execution_context
        from butler.runtime.task_store import complete_task, create_task

        attach_turn_memory_prefetch(agent, orch, raw_user_msg, role=role)

        session_key = str(get_current_session_key() or "").strip()
        project_name = ""
        if project is not None:
            project_name = str(getattr(project, "name", "") or "")
        task_record = create_task(
            session_key=session_key,
            role=role,
            task_preview=task,
            project=project_name,
        )
        task_id = str(task_record.get("task_id") or "")

        with use_execution_context(orch, session_key=session_key):
            result = agent.run(user_msg)
        sync_turn_memory(
            orch,
            raw_user_msg,
            result.final_response or "",
            interrupted=result.status.value == "interrupted",
            status=result.status,
            session_id=session_key,
        )

        from butler.report import AgentReport

        changes = _extract_changes_from_messages(result.messages)
        issues = _extract_issues_from_messages(result.messages)
        success = _delegate_task_succeeded(result, changes, issues)
        role_label = _delegate_role_label(role)
        headline = (
            f"{role_label}已完成任务"
            if success
            else f"{role_label}未能完成任务"
        )
        task_preview = (task or "").strip()[:200]
        report = AgentReport(
            headline=headline,
            summary=result.final_response or "(无输出)",
            changes=changes,
            issues=issues,
            success=success,
            task_preview=task_preview,
            task_id=task_id,
            iterations=result.iterations,
            tool_calls=result.tool_calls_made,
            tokens_used=result.total_tokens,
            elapsed_seconds=result.elapsed_seconds,
        )

        from butler.report import cache_report
        cache_report(report, session_key=session_key)
        complete_task(
            task_id,
            success=success,
            report_headline=report.headline,
            summary=report.summary,
        )

        return json.dumps({
            "success": report.success,
            "headline": report.headline,
            "summary": report.summary[:2000],
            "task_id": task_id,
            "iterations": report.iterations,
            "tool_calls": report.tool_calls,
            "tokens": report.tokens_used,
        }, ensure_ascii=False)

    except Exception as exc:
        logger.error("Delegation to %s failed: %s", role, exc)
        return _finalize_delegate_failure(
            role=role,
            task=task,
            exc=exc,
            task_id=task_id,
            session_key=session_key,
        )


def _orchestrator_for_tool(*, channel: str):
    from butler.execution_context import get_current_orchestrator

    orch = get_current_orchestrator()
    if orch is not None:
        return orch

    from butler.orchestrator import ButlerOrchestrator

    return ButlerOrchestrator(user_id="owner", channel=channel)


def _project_agent_raw_message(*, task: str, context: str = "") -> str:
    user_msg = task
    if context:
        user_msg = f"## 上下文\n{context}\n\n## 任务\n{task}"
    return user_msg


def _inject_project_agent_skills(orch: Any, user_msg: str) -> str:
    inject = getattr(orch, "inject_skill_context", None)
    if callable(inject):
        return inject(user_msg)
    return user_msg


def _safe_dispatch(name: str, args: dict, depth: int) -> str:
    from butler.delegate_policy import DELEGATE_BLOCKED_TOOLS
    if name in DELEGATE_BLOCKED_TOOLS:
        return json.dumps({"error": f"Tool '{name}' is blocked in delegated agents"})
    if name == "delegate_task":
        args = {**args, "depth": depth}
    return dispatch_tool(name, args)


def _delegate_role_label(role: str) -> str:
    key = str(role or "").strip().lower()
    labels = {
        "content_agent": "内容代理",
        "content": "内容代理",
        "dev_agent": "开发代理",
        "dev": "开发代理",
        "review_agent": "审核代理",
        "review": "审核代理",
        "butler": "管家",
    }
    return labels.get(key, str(role or "代理"))


def _extract_issues_from_messages(messages: list) -> list[str]:
    import json as _json

    issues: list[str] = []
    seen: set[str] = set()
    for msg in messages or []:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        err = ""
        try:
            payload = _json.loads(content)
            if isinstance(payload, dict):
                err = str(payload.get("error") or "").strip()
        except _json.JSONDecodeError:
            pass
        if not err and '"error"' in content.lower():
            err = content[:400].strip()
        if err and err not in seen:
            seen.add(err)
            issues.append(err[:500])
    return issues[:5]


def _delegate_task_succeeded(result: Any, changes: list, issues: list) -> bool:
    if result.status.value != "completed":
        return False
    if issues and not changes:
        return False
    return True


def _extract_changes_from_messages(messages: list) -> list:
    import json as _json

    from butler.report import Change

    changes: list[Change] = []
    for msg in messages or []:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        lowered = content.lower()
        if '"success": true' not in lowered and '"success":true' not in lowered:
            continue
        path = ""
        action = "modified"
        try:
            payload = _json.loads(content)
            if isinstance(payload, dict):
                path = str(payload.get("path") or "").strip()
                raw_action = str(payload.get("action") or "").strip().lower()
                if raw_action in {"created", "modified", "deleted"}:
                    action = raw_action
                elif payload.get("replacements"):
                    action = "modified"
                elif payload.get("bytes") is not None and not payload.get("replacements"):
                    action = "created"
        except _json.JSONDecodeError:
            pass
        if not path and "write_file" in lowered:
            action = "created"
        if not path and "delete_file" in lowered:
            action = "deleted"
        if not path:
            path = "(文件变更)"
        changes.append(
            Change(
                file=path,
                action=action if action in {"created", "modified", "deleted"} else "modified",
                description="",
            )
        )
    return changes[:10]
