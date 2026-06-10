"""Terminal, search, and directory listing tool implementations."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_TERMINAL_TIMEOUT_SECONDS = 120
MAX_TERMINAL_OUTPUT_CHARS = 50000


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


def _tool_terminal(command: str, timeout: int = 30, workdir: str = None, **_) -> str:
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
            finally:
                _close_pipe(proc.stdout)
                _close_pipe(proc.stderr)
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
