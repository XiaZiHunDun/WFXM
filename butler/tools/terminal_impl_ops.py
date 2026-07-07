"""Terminal tool subprocess helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def is_selectable_pipe_safe(pipe: Any) -> bool:
    def _run() -> bool:
        return isinstance(pipe.fileno(), int)

    result = safe_best_effort(_run, label="terminal_impl.selectable_pipe", default=False)
    return bool(result)


def close_pipe_safe(pipe: Any) -> None:
    def _run() -> None:
        if pipe is not None:
            pipe.close()

    safe_best_effort(_run, label="terminal_impl.close_pipe", default=None)


def inc_terminal_metric_safe(name: str, *, labels: dict[str, str] | None = None, session_key: str = "") -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        inc(name, labels=labels, session_key=session_key)

    safe_best_effort(_run, label=f"terminal_impl.metric.{name}", default=None)


def run_subprocess_loud(run_fn: Callable[[], str]) -> str:
    try:
        return run_fn()
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def run_terminal_with_gates_safe(
    cmd_text: str,
    *,
    cwd: str,
    session_key: str,
    run_fn: Callable[[], str],
) -> str:
    def _run() -> str:
        from butler.core.tool_orchestrator import run_terminal_with_gates

        return str(
            run_terminal_with_gates(
                cmd_text,
                cwd=cwd,
                session_key=session_key,
                run_fn=run_fn,
            )
        )

    result = safe_best_effort(_run, label="terminal_impl.terminal_gates", default=None)
    if isinstance(result, str):
        return result
    return run_fn()


def search_files_error_payload(exc: BaseException) -> str:
    return json.dumps({"error": str(exc)})


def list_directory_error_payload(exc: BaseException) -> str:
    return json.dumps({"error": str(exc)})


def run_search_files_loud(run: Callable[[], str]) -> str:
    try:
        return run()
    except FileNotFoundError:
        return json.dumps({"error": "ripgrep (rg) not installed"})
    except Exception as exc:
        return search_files_error_payload(exc)


def run_list_directory_loud(run: Callable[[], str]) -> str:
    try:
        return run()
    except Exception as exc:
        return list_directory_error_payload(exc)
