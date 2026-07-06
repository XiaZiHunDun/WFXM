"""Terminal, search, and directory listing tool implementations."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import IO, Any, cast

logger = logging.getLogger(__name__)

MAX_TERMINAL_TIMEOUT_SECONDS = 120
MAX_TERMINAL_OUTPUT_CHARS = 50000


def _is_selectable_pipe(pipe: Any) -> bool:
    from butler.tools.terminal_impl_ops import is_selectable_pipe_safe

    return bool(is_selectable_pipe_safe(pipe))


def _close_pipe(pipe: Any) -> None:
    from butler.tools.terminal_impl_ops import close_pipe_safe

    close_pipe_safe(pipe)


def _communicate_limited(
    proc: subprocess.Popen[Any],
    *,
    timeout: int,
    max_output_chars: int,
) -> tuple[str, str, bool]:
    """Read process pipes incrementally so tool output cannot exhaust memory."""
    stdout_pipe = proc.stdout
    stderr_pipe = proc.stderr
    if not (
        stdout_pipe is not None
        and stderr_pipe is not None
        and _is_selectable_pipe(stdout_pipe)
        and _is_selectable_pipe(stderr_pipe)
    ):
        stdout, stderr = proc.communicate(timeout=timeout)
        return str(stdout or ""), str(stderr or ""), (
            len(str(stdout or "")) + len(str(stderr or "")) > max_output_chars
        )

    import selectors

    selector = selectors.DefaultSelector()
    stdout_io = stdout_pipe
    stderr_io = stderr_pipe
    selector.register(stdout_io, selectors.EVENT_READ, "stdout")
    selector.register(stderr_io, selectors.EVENT_READ, "stderr")
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
                assert isinstance(pipe, IO)
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


def _tool_terminal(command: str, timeout: int = 30, workdir: str | None = None, **_: Any) -> str:
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
    workspace_path = safety.path

    from butler.tools.terminal_approval import approval_allows_unsandboxed
    from butler.tools.terminal_sandbox import (
        classify_sandbox_failure,
        enrich_subprocess_env,
        format_sandbox_error_payload,
        load_terminal_sandbox_config,
        sandbox_runtime_available,
        scrub_credential_env,
        should_run_sandboxed,
        wrap_argv_with_bubblewrap,
    )

    sandbox_config = load_terminal_sandbox_config(workspace_path)
    unsandboxed = approval_allows_unsandboxed(
        cmd_text,
        cwd=resolved_workdir,
        session_key=session_key,
    )
    run_sandboxed = should_run_sandboxed(
        sandbox_config,
        unsandboxed_approved=unsandboxed,
    )
    if run_sandboxed and not sandbox_runtime_available():
        if sandbox_config.fail_if_unavailable:
            return json.dumps({
                "error": "bubblewrap (bwrap) 未安装，且 BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE=1",
                "code": "SANDBOX_UNAVAILABLE",
            })
        logger.warning("terminal sandbox enabled but bwrap missing; running unsandboxed")
        run_sandboxed = False
        from butler.tools.terminal_impl_ops import inc_terminal_metric_safe

        inc_terminal_metric_safe("terminal_sandbox_unavailable_fallback")

    exec_argv = list(command_safety.argv)
    if run_sandboxed:
        try:
            exec_argv = wrap_argv_with_bubblewrap(
                exec_argv,
                workspace=workspace_path,
                config=sandbox_config,
            )
        except RuntimeError as exc:
            return json.dumps({"error": str(exc), "code": "SANDBOX_UNAVAILABLE"})

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
        base_env = safe_subprocess_env()
        if run_sandboxed:
            base_env = scrub_credential_env(base_env, sandbox_config)
        proc_env = enrich_subprocess_env(base_env, sandboxed=run_sandboxed)
        if run_sandboxed:
            from butler.tools.terminal_impl_ops import inc_terminal_metric_safe

            inc_terminal_metric_safe(
                "terminal_sandbox_run",
                labels={"sandboxed": "1"},
                session_key=session_key,
            )
        proc = subprocess.Popen(
            exec_argv,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=resolved_workdir,
            env=proc_env,
        )
        assert proc is not None
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
            failure = classify_sandbox_failure(
                exit_code=proc.returncode,
                stdout=stdout or "",
                stderr=stderr or "",
                sandboxed=run_sandboxed,
            )
            if failure is not None:
                from butler.tools.terminal_impl_ops import inc_terminal_metric_safe

                inc_terminal_metric_safe(
                    "terminal_sandbox_failure",
                    labels={"constraint": failure.constraint},
                    session_key=session_key,
                )
                return json.dumps(
                    format_sandbox_error_payload(
                        failure,
                        command=cmd_text,
                        exit_code=proc.returncode,
                        output=output,
                    ),
                    ensure_ascii=False,
                )
            return json.dumps({
                "exit_code": proc.returncode,
                "output": output,
                "sandboxed": run_sandboxed,
            })
        finally:
            _close_pipe(proc.stdout)
            _close_pipe(proc.stderr)

    from butler.tools.terminal_impl_ops import run_subprocess_loud, run_terminal_with_gates_safe

    return str(
        run_terminal_with_gates_safe(
            cmd_text,
            cwd=cwd_hint,
            session_key=session_key,
            run_fn=lambda: run_subprocess_loud(_run_subprocess),
        )
    )


def _tool_search_files(pattern: str, path: str = ".", include: str | None = None, **_: Any) -> str:
    from butler.tools.path_safety import check_tool_path, safe_subprocess_env

    safety = check_tool_path(path)
    if not safety.allowed:
        return json.dumps({"error": safety.error})
    cmd = ["rg", "--no-config", "--json", "-m", "20"]
    if include:
        cmd.extend(["--glob", include])
    cmd.extend(["--", pattern, str(safety.path)])

    def _run() -> str:
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

    from butler.tools.terminal_impl_ops import run_search_files_loud

    return str(run_search_files_loud(_run))


def _tool_list_directory(path: str = ".", **_: Any) -> str:
    from butler.tools.path_safety import check_tool_path

    safety = check_tool_path(path)
    if not safety.allowed:
        return json.dumps({"error": safety.error})
    p = safety.path
    if not p.is_dir():
        return json.dumps({"error": f"Not a directory: {path}"})

    def _run() -> str:
        entries = []
        for item in sorted(p.iterdir()):
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
        return json.dumps({"path": str(p), "entries": entries[:200]})

    from butler.tools.terminal_impl_ops import run_list_directory_loud

    return str(run_list_directory_loud(_run))
