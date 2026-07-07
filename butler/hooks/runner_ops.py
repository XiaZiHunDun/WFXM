"""Shell hook runner helpers (P0-A)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, cast

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def resolve_hooks_workspace_safe() -> Path | None:
    def _run() -> Path | None:
        from butler.execution_context import (
            get_current_orchestrator,
            get_current_session_key,
        )

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return None
        return Path(proj.workspace)

    return cast(Path, safe_best_effort(_run, label="hooks.runner.workspace", default=None))


def session_key_from_payload_safe(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("session_key") or "").strip()
    if explicit:
        return explicit

    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()

    return safe_best_effort(_run, label="hooks.runner.session_key", default="") or ""


def record_hook_run_safe(
    *,
    session_key: str,
    event: str,
    exit_code: int | None,
    preview: str,
) -> None:
    def _run() -> None:
        from butler.hooks.telemetry import record_hook_run

        record_hook_run(
            session_key=session_key,
            event=event,
            exit_code=exit_code,
            preview=preview,
        )

    safe_best_effort(_run, label="hooks.runner.telemetry", default=None)


def run_hook_command_safe(
    *,
    command: str,
    cwd: str,
    payload: dict[str, Any],
    event: str,
) -> tuple[int | None, str, str]:
    stdin_json = json.dumps(payload, ensure_ascii=False)
    from butler.tools.path_safety import safe_subprocess_env

    env = safe_subprocess_env()
    env.update({
        "BUTLER_HOOK_EVENT": str(payload.get("hook_event_name") or event),
        "BUTLER_HOOK_TOOL": str(payload.get("tool_name") or ""),
        "BUTLER_HOOK_INPUT": stdin_json[:8000],
    })
    session_key = session_key_from_payload_safe(payload)
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            shell=False,
            cwd=cwd,
            input=stdin_json,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        code = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        preview = (stderr or stdout or "").strip()[:120]
        record_hook_run_safe(
            session_key=session_key,
            event=str(payload.get("hook_event_name") or event),
            exit_code=code,
            preview=preview,
        )
        return code, stdout, stderr
    except subprocess.TimeoutExpired:
        record_hook_run_safe(
            session_key=session_key,
            event=str(payload.get("hook_event_name") or event),
            exit_code=None,
            preview="hook timed out",
        )
        return None, "", "hook timed out"
    except Exception as exc:
        logger.warning("Hook command failed: %s", exc)
        record_hook_run_safe(
            session_key=session_key,
            event=str(payload.get("hook_event_name") or event),
            exit_code=None,
            preview=str(exc)[:120],
        )
        return None, "", str(exc)
