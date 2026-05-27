"""Built-in tool implementations extracted from registry.py.

Contains: file I/O tools, terminal, search, delegate, workflow,
and their helper functions.
"""

from __future__ import annotations

import json
import logging
import os
import stat as stat_module
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_READ_FILE_BYTES = 1024 * 1024
MAX_READ_FILE_LINES = 1000
MAX_TERMINAL_TIMEOUT_SECONDS = 120
MAX_TERMINAL_OUTPUT_CHARS = 50000

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
        from butler.core.read_file_partial import (
            build_large_file_summary,
            format_summary_message,
            read_summary_threshold_lines,
        )

        if (
            offset == 1
            and len(lines) > read_summary_threshold_lines()
            and limit >= 100
        ):
            summary = build_large_file_summary(str(path), lines)
            return format_summary_message(summary)
        start = offset - 1
        end = start + limit
        selected = lines[start:end]
        if _p is not None:
            from butler.core.hashline import format_read_output

            body = format_read_output(_p, selected, start + 1)
        else:
            from butler.core.hashline import hashline_read_enabled

            if hashline_read_enabled():
                from butler.core.hashline import format_hash_line

                body = "\n".join(
                    format_hash_line(start + i + 1, line)
                    for i, line in enumerate(selected)
                )
            else:
                body = "\n".join(
                    f"{i + start + 1:6}|{line}" for i, line in enumerate(selected)
                )
        if _p is not None and _stat is not None:
            from butler.core.read_state import record_read_state

            record_read_state(_p, _stat, data)
            try:
                from butler.core.instruction_walkup import record_read_path
                from butler.execution_context import get_current_orchestrator

                orch = get_current_orchestrator()
                workspace_root = None
                if orch is not None:
                    pm = getattr(orch, "project_manager", None)
                    proj = pm.get_current() if pm is not None else None
                    if proj is not None:
                        workspace_root = Path(proj.workspace)
                record_read_path(_p, workspace_root=workspace_root)
            except Exception:
                pass
        return body
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
        from butler.core.read_state import require_read_before_edit

        guard = require_read_before_edit(path, for_write=True)
        if guard:
            return json.dumps(guard, ensure_ascii=False)
        p, error = _atomic_write_text(path, content)
        if error:
            return json.dumps({"error": error})
        try:
            from butler.core.read_state import record_edit_path

            record_edit_path(p)
        except Exception:
            pass
        payload: dict = {"success": True, "path": str(p), "bytes": len(content.encode("utf-8"))}
        try:
            from butler.core.post_edit_format import maybe_format_after_edit

            fmt = maybe_format_after_edit(p)
            if fmt:
                payload["post_edit_format"] = fmt
        except Exception:
            pass
        return json.dumps(payload)
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
        from butler.core.read_state import normalize_quotes, require_read_before_edit

        guard = require_read_before_edit(path, for_write=True)
        if guard:
            return json.dumps(guard, ensure_ascii=False)
        data, _p, expected_stat, error = _read_regular_file_bytes(path, for_write=True)
        if error:
            return json.dumps({"error": error})
        if _p is not None:
            try:
                from butler.core.hashline import extract_anchors_from_old_string, verify_line_anchors

                anchors = extract_anchors_from_old_string(old_string)
                mismatch = verify_line_anchors(_p, anchors)
                if mismatch:
                    return json.dumps(mismatch, ensure_ascii=False)
            except Exception:
                pass
        text = data.decode("utf-8", errors="replace")
        count = text.count(old_string)
        fuzzy = False
        if count == 0:
            norm_text = normalize_quotes(text)
            norm_old = normalize_quotes(old_string)
            count = norm_text.count(norm_old)
            if count > 0:
                text = norm_text
                old_string = norm_old
                new_string = normalize_quotes(new_string)
                fuzzy = True
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
        try:
            from butler.core.read_state import record_edit_path

            if _written_path is not None:
                record_edit_path(_written_path)
        except Exception:
            pass
        payload: dict[str, Any] = {"success": True, "replacements": 1}
        if fuzzy:
            payload["fuzzy_quotes"] = True
        if _written_path is not None:
            try:
                from butler.core.post_edit_format import maybe_format_after_edit

                fmt = maybe_format_after_edit(_written_path)
                if fmt:
                    payload["post_edit_format"] = fmt
            except Exception:
                pass
        return json.dumps(payload)
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

    cwd_hint = str(workdir or default_tool_workdir() or "")
    cmd_text = " ".join(command_safety.argv) if command_safety.argv else command
    from butler.execution_context import get_current_session_key

    session_key = str(get_current_session_key() or "")

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

    def _run_subprocess() -> str:
        nonlocal proc, interrupted
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

    try:
        from butler.core.tool_orchestrator import run_terminal_with_gates

        return run_terminal_with_gates(
            cmd_text,
            cwd=cwd_hint,
            session_key=session_key,
            run_fn=_run_subprocess,
        )
    except Exception:
        return _run_subprocess()


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
    from butler.execution_context import get_current_session_key
    from butler.gateway.outbound_bridge import get_gateway_bridge_optional

    bridge = get_gateway_bridge_optional()
    session_key = ""
    try:
        from butler.workflows.runner import run_workflow_for_project

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
        if bridge is not None:
            from butler.report import get_last_report

            report = get_last_report(session_key)
            if report is not None:
                bridge.notify_workflow_finished(report)
        return json.dumps({"success": True, "summary": text}, ensure_ascii=False)
    except Exception as exc:
        try:
            from butler.gateway.completion_notify import try_push_workflow_failure

            try_push_workflow_failure(
                bridge,
                name,
                exc,
                session_key=session_key or str(get_current_session_key() or ""),
            )
        except Exception as push_exc:
            logger.debug("Workflow failure completion push skipped: %s", push_exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _run_subagent_stop_hooks(
    *,
    role: str,
    agent_id: str,
    success: bool,
    task_id: str = "",
    session_key: str = "",
    summary_preview: str = "",
) -> None:
    try:
        from butler.hooks.runner import run_subagent_stop_hooks

        run_subagent_stop_hooks(
            agent_type=role,
            agent_id=agent_id,
            success=success,
            task_id=task_id,
            session_key=session_key,
            summary_preview=summary_preview,
        )
    except Exception as exc:
        logger.debug("SubagentStop hooks skipped: %s", exc)


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
    _run_subagent_stop_hooks(
        role=role,
        agent_id=task_id or f"delegate-{role}",
        success=False,
        task_id=task_id,
        session_key=session_key,
        summary_preview=summary,
    )
    try:
        from butler.gateway.outbound_bridge import get_gateway_bridge_optional

        br = get_gateway_bridge_optional()
        if br is not None:
            br.notify_delegate_finished(report)
    except Exception:
        pass
    payload: dict[str, Any] = {
        "success": False,
        "error": f"Delegation failed: {exc}",
        "headline": headline,
    }
    if task_id:
        payload["task_id"] = task_id
    return json.dumps(payload, ensure_ascii=False)


def _tool_delegate_task(
    role: str,
    task: str,
    context: str = "",
    category: str = "",
    depth: int = 0,
    **_,
) -> str:
    """Delegate to a project-level agent through Butler's orchestrator."""
    task_id = ""
    session_key = ""
    category_meta: dict[str, Any] = {}
    original_context = context
    try:
        from butler.delegate_policy import MAX_DELEGATE_DEPTH
        from butler.gateway.outbound_bridge import get_gateway_bridge_optional

        if not str(category or "").strip():
            try:
                from butler.core.intent_keywords import category_from_intent

                inferred = category_from_intent(task)
                if inferred:
                    category = inferred
            except Exception:
                pass

        if str(category or "").strip():
            from butler.delegate_category_resolver import apply_category_to_delegate

            role, task, context, category_meta = apply_category_to_delegate(
                category=str(category).strip(),
                role=role,
                task=task,
                context=context,
            )

        from butler.core.handoff import merge_handoff_into_context, render_handoff_block

        cat_name = str(category or category_meta.get("category") or "").strip().lower()
        needs_handoff = (
            cat_name.startswith("nexus")
            or cat_name == "ui-build"
            or "## Handoff" not in str(context or "")
        )
        if needs_handoff:
            from butler.core.handoff import default_visual_acceptance

            if cat_name == "ui-build":
                acceptance = default_visual_acceptance()
                evidence_required = ["read_file DESIGN.md", "read_file 改动文件"]
            else:
                acceptance = [
                    "任务描述中的目标已达成",
                    "关键改动有 read_file 或测试证据",
                ]
                evidence_required = ["read_file 或 pytest"]
            handoff = render_handoff_block(
                from_role="butler",
                to_role=str(role or "dev"),
                task=task,
                acceptance=acceptance,
                evidence_required=evidence_required,
            )
            context = merge_handoff_into_context(context, handoff)

        try:
            from butler.agent_profiles import DELEGATE_VERIFY_CHECKLIST

            if DELEGATE_VERIFY_CHECKLIST.strip():
                context = (context or "").rstrip() + "\n\n" + DELEGATE_VERIFY_CHECKLIST.strip()
        except Exception:
            pass

        bridge = get_gateway_bridge_optional()
        if bridge is not None:
            bridge.notify_delegate_start(role, preview=task[:80])

        if depth >= MAX_DELEGATE_DEPTH:
            return json.dumps({"error": f"Maximum delegation depth ({MAX_DELEGATE_DEPTH}) exceeded"})

        orch = _orchestrator_for_tool(channel="cli")
        from butler.tools.project_tools import get_tool_definitions_for_project

        project = orch.project_manager.get_current()
        if project is not None:
            try:
                from butler.agents_md import merge_agent_md_into_context

                context = merge_agent_md_into_context(
                    Path(project.workspace),
                    role,
                    context,
                )
            except Exception:
                pass
        tools = get_tool_definitions_for_project(project, role=role)

        from butler.delegate_subagent_permissions import filter_tools_for_subagent

        workspace = Path(project.workspace) if project is not None else None
        delegated_tools = filter_tools_for_subagent(
            tools,
            workspace=workspace,
            role=role,
        )
        allow_only = category_meta.get("allow_tools")
        deny_extra = category_meta.get("deny_tools")
        if isinstance(allow_only, list) and allow_only:
            allow_set = {str(t).strip() for t in allow_only if str(t).strip()}
            delegated_tools = [
                t
                for t in delegated_tools
                if str((t.get("function") or {}).get("name") or "") in allow_set
            ]
        if isinstance(deny_extra, list):
            deny_set = {str(t).strip() for t in deny_extra if str(t).strip()}
            delegated_tools = [
                t
                for t in delegated_tools
                if str((t.get("function") or {}).get("name") or "") not in deny_set
            ]

        from butler.core.delegate_context import child_callbacks, get_parent_callbacks

        parent_cb = get_parent_callbacks()
        agent = orch.create_project_agent_loop(
            role=role,
            tools=delegated_tools,
            tool_dispatcher=lambda name, args: _safe_dispatch(name, args, depth + 1),
            callbacks=child_callbacks(parent_cb),
        )
        from butler.core.cache_safe_delegate import (
            apply_cache_safe_system_prompt,
            delegate_diagnostics,
        )
        from butler.core.delegate_context import get_parent_system_prompt

        from butler.core.delegate_context import get_parent_messages

        parent_sys = get_parent_system_prompt()
        parent_msgs = get_parent_messages()
        if parent_sys:
            merged = apply_cache_safe_system_prompt(
                parent_sys,
                agent.system_prompt,
                tools=delegated_tools,
                messages=parent_msgs,
            )
            agent.system_prompt = merged
            agent.diagnostics.update(
                delegate_diagnostics(
                    parent_sys,
                    merged,
                    tools=delegated_tools,
                    messages=parent_msgs,
                )
            )
        from butler.delegate_policy import resolve_delegate_max_iterations

        agent.config.max_iterations = resolve_delegate_max_iterations(category_meta)
        try:
            from butler.delegate_policy import delegate_one_tool_per_iteration

            if delegate_one_tool_per_iteration():
                agent.config.enable_parallel_tools = False
                agent.diagnostics["delegate_one_tool_per_iteration"] = True
        except Exception:
            pass

        agent.reset()

        raw_user_msg = _project_agent_raw_message(task=task, context=context)
        memory_sync_user_msg = _project_agent_raw_message(
            task=task,
            context=original_context,
        )
        user_msg = _inject_project_agent_skills(orch, raw_user_msg)

        from butler.session_lifecycle import attach_turn_memory_prefetch, sync_turn_memory
        from butler.execution_context import get_current_session_key, use_execution_context
        from butler.runtime.task_store import complete_task, create_task

        attach_turn_memory_prefetch(agent, orch, raw_user_msg, role=role)

        session_key = str(get_current_session_key() or "").strip()
        from butler.core.delegate_semaphore import try_acquire_delegate_slot

        if not try_acquire_delegate_slot(session_key):
            from butler.core.delegate_semaphore import max_concurrent_delegates

            return json.dumps({
                "error": (
                    f"本会话并发委派已达上限 ({max_concurrent_delegates()})，"
                    "请等待进行中的任务完成。"
                ),
                "code": "DELEGATE_CONCURRENCY",
            })
        project_name = ""
        if project is not None:
            project_name = str(getattr(project, "name", "") or "")
        from butler.runtime.task_store import delegate_group_id

        group_id = delegate_group_id(session_key)
        task_record = create_task(
            session_key=session_key,
            role=role,
            task_preview=task,
            project=project_name,
            group_id=group_id,
        )
        task_id = str(task_record.get("task_id") or "")
        child_session_key = str(task_record.get("child_session_key") or "")

        try:
            from butler.hooks.runner import run_subagent_start_hooks

            subagent_ctx = run_subagent_start_hooks(
                agent_type=role,
                agent_id=task_id or f"delegate-{role}",
                task_preview=task,
                task_id=task_id,
                session_key=session_key,
            )
            if subagent_ctx:
                user_msg = "\n\n".join(subagent_ctx) + "\n\n" + user_msg
        except Exception as exc:
            logger.debug("SubagentStart hooks skipped: %s", exc)

        from butler.core.session_transcript import record_generic_event

        if child_session_key:
            record_generic_event(
                session_key,
                "delegate_started",
                {
                    "task_id": task_id,
                    "child_session_key": child_session_key,
                    "role": role,
                },
            )
            record_generic_event(
                child_session_key,
                "delegate_turn_start",
                {"task_id": task_id, "parent_session_key": session_key, "role": role},
            )

        from butler.runtime.async_delegate import (
            schedule_background_delegate,
            should_delegate_async,
            push_target_from_bridge,
        )
        from butler.runtime.delegate_job import (
            DelegateJob,
            build_async_delegate_tool_result,
        )

        if should_delegate_async(
            bridge=bridge,
            depth=depth,
            category_meta=category_meta,
        ):
            push_tgt = push_target_from_bridge(bridge) if bridge is not None else None
            schedule_background_delegate(
                DelegateJob(
                    agent=agent,
                    orch=orch,
                    user_msg=user_msg,
                    raw_user_msg=raw_user_msg,
                    role=role,
                    task=task,
                    session_key=session_key,
                    child_session_key=child_session_key,
                    task_id=task_id,
                    category_meta=category_meta,
                    bridge=bridge,
                    push_target=push_tgt,
                )
            )
            return build_async_delegate_tool_result(
                task_id=task_id,
                child_session_key=child_session_key,
                role=role,
                task_preview=task,
                category=str(category_meta.get("category") or category or ""),
            )

        try:
            with use_execution_context(orch, session_key=child_session_key or session_key):
                try:
                    from butler.runtime.delegate_registry import (
                        register_delegate_loop,
                        unregister_delegate_loop,
                    )

                    register_delegate_loop(session_key, agent)
                    result = agent.run(user_msg)
                finally:
                    try:
                        from butler.runtime.delegate_registry import unregister_delegate_loop

                        unregister_delegate_loop(session_key, agent)
                    except Exception:
                        pass
        finally:
            from butler.core.delegate_semaphore import release_delegate_slot

            release_delegate_slot(session_key)

        sync_turn_memory(
            orch,
            memory_sync_user_msg,
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
        summary_text = (result.final_response or "").strip()
        if not summary_text:
            summary_text = (
                "DELEGATE_EMPTY_RESPONSE: 子代理未返回有效摘要。"
                "请缩小任务范围或换 category/role 后重试。"
            )
            success = False
            headline = f"{role_label}返回空结果"

        if child_session_key:
            record_generic_event(
                child_session_key,
                "delegate_turn_done",
                {
                    "task_id": task_id,
                    "success": success,
                    "iterations": getattr(result, "iterations", 0),
                },
            )

        report = AgentReport(
            headline=headline,
            summary=summary_text or "(无输出)",
            changes=changes,
            issues=issues,
            success=success,
            task_preview=task_preview,
            task_id=task_id,
            child_session_key=child_session_key,
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
        _run_subagent_stop_hooks(
            role=role,
            agent_id=task_id or f"delegate-{role}",
            success=success,
            task_id=task_id,
            session_key=session_key,
            summary_preview=report.summary,
        )
        if bridge is not None:
            bridge.notify_delegate_finished(report)

        payload: dict[str, Any] = {
            "success": report.success,
            "headline": report.headline,
            "summary": report.summary[:2000],
            "task_id": task_id,
            "child_session_key": child_session_key,
            "iterations": report.iterations,
            "tool_calls": report.tool_calls,
            "tokens": report.tokens_used,
        }
        if category_meta.get("category"):
            payload["category"] = category_meta["category"]
        if not (result.final_response or "").strip():
            payload["code"] = "DELEGATE_EMPTY_RESPONSE"
        return json.dumps(payload, ensure_ascii=False)

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
    from butler.tools.registry import dispatch_tool as _dispatch
    result = _dispatch(name, args)
    try:
        from butler.memory.corrective_recall import (
            build_corrective_recall_block,
            should_trigger_corrective,
        )

        if should_trigger_corrective(name, result):
            task_hint = str(args.get("task") or args.get("query") or args.get("path") or "")
            block = build_corrective_recall_block(
                task=task_hint,
                tool_name=name,
                error_excerpt=result[:400],
            )
            if block:
                result = f"{result}\n\n{block}"
    except Exception:
        pass
    return result


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
