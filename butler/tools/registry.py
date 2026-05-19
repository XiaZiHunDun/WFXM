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
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)
MAX_READ_FILE_BYTES = 1024 * 1024
MAX_READ_FILE_LINES = 1000
MAX_TERMINAL_TIMEOUT_SECONDS = 120
MAX_TERMINAL_OUTPUT_CHARS = 50000


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
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = entry.handler(**args)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        return json.dumps({"error": f"Tool '{name}' failed: {exc}"})


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


# ── Tool Implementations ─────────────────────────────────────

def _tool_read_file(path: str, offset: int = 1, limit: int = 500, **_) -> str:
    from butler.tools.path_safety import check_tool_path, tool_safe_root

    safety = check_tool_path(path)
    if not safety.allowed:
        return json.dumps({"error": safety.error})
    p = safety.path
    if not p.exists():
        return json.dumps({"error": f"File not found: {path}"})
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

        expected_stat = p.stat()
        raw_open_path = _raw_tool_path(path, tool_safe_root())
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            fd = os.open(raw_open_path, flags)
        except OSError as exc:
            if "Too many levels of symbolic links" in str(exc):
                return json.dumps({"error": "Access denied: symlinks are not allowed"})
            return json.dumps({"error": str(exc)})

        try:
            stat_result = os.fstat(fd)
            if (stat_result.st_dev, stat_result.st_ino) != (
                expected_stat.st_dev,
                expected_stat.st_ino,
            ):
                return json.dumps({"error": "Access denied: file changed during validation"})
            if not stat_module.S_ISREG(stat_result.st_mode):
                return json.dumps({"error": "Access denied: only regular files can be read"})
            if stat_result.st_nlink > 1:
                return json.dumps({"error": "Access denied: hardlinked files are not allowed"})
            if stat_result.st_size > MAX_READ_FILE_BYTES:
                return json.dumps({
                    "error": f"File too large: maximum is {MAX_READ_FILE_BYTES} bytes"
                })
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(fd, min(65536, MAX_READ_FILE_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_READ_FILE_BYTES:
                    return json.dumps({
                        "error": f"File too large: maximum is {MAX_READ_FILE_BYTES} bytes"
                    })
        finally:
            os.close(fd)

        text = b"".join(chunks).decode("utf-8", errors="replace")
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


def _tool_write_file(path: str, content: str, **_) -> str:
    from butler.tools.path_safety import check_tool_path

    safety = check_tool_path(path, for_write=True)
    if not safety.allowed:
        return json.dumps({"error": safety.error})
    p = safety.path
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return json.dumps({"success": True, "path": str(p), "bytes": len(content.encode("utf-8"))})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_patch(path: str, old_string: str, new_string: str, **_) -> str:
    from butler.tools.path_safety import check_tool_path

    safety = check_tool_path(path, for_write=True)
    if not safety.allowed:
        return json.dumps({"error": safety.error})
    p = safety.path
    if not p.exists():
        return json.dumps({"error": f"File not found: {path}"})
    try:
        text = p.read_text(encoding="utf-8")
        count = text.count(old_string)
        if count == 0:
            return json.dumps({"error": "old_string not found in file"})
        if count > 1:
            return json.dumps({"error": f"old_string found {count} times; must be unique"})
        new_text = text.replace(old_string, new_string, 1)
        p.write_text(new_text, encoding="utf-8")
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


def _tool_delegate_task(role: str, task: str, context: str = "", depth: int = 0, **_) -> str:
    """Delegate to a project-level agent through Butler's orchestrator."""
    try:
        from butler.delegate_policy import DELEGATE_BLOCKED_TOOLS, MAX_DELEGATE_DEPTH

        if depth >= MAX_DELEGATE_DEPTH:
            return json.dumps({"error": f"Maximum delegation depth ({MAX_DELEGATE_DEPTH}) exceeded"})

        orch = _orchestrator_for_tool(channel="cli")
        tools = get_tool_definitions()

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

        attach_turn_memory_prefetch(agent, orch, raw_user_msg, role=role)

        session_key = get_current_session_key()
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
        report = AgentReport(
            headline=f"{role} 代理完成任务",
            summary=result.final_response or "(无输出)",
            changes=changes,
            success=result.status.value == "completed",
            iterations=result.iterations,
            tool_calls=result.tool_calls_made,
            tokens_used=result.total_tokens,
            elapsed_seconds=result.elapsed_seconds,
        )

        from butler.report import cache_report
        cache_report(report)

        return json.dumps({
            "success": report.success,
            "headline": report.headline,
            "summary": report.summary[:2000],
            "iterations": report.iterations,
            "tool_calls": report.tool_calls,
            "tokens": report.tokens_used,
        }, ensure_ascii=False)

    except Exception as exc:
        logger.error("Delegation to %s failed: %s", role, exc)
        return json.dumps({"error": f"Delegation failed: {exc}"})


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


def _extract_changes_from_messages(messages: list) -> list:
    from butler.report import Change
    changes: list[Change] = []
    for msg in messages or []:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        if "write_file" in content or "patch" in content:
            if '"success": true' in content.lower() or '"success":true' in content.lower():
                changes.append(Change(file="(tool)", action="modified", description=content[:120]))
    return changes[:10]
