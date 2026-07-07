"""Execute-code workspace/subprocess best-effort helpers (P0-A)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def resolve_execute_code_workspace_safe() -> Path | None:
    def _run() -> Path:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        pm = getattr(orch, "project_manager", None) if orch else None
        if pm is None:
            raise ValueError("no project manager")
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            raise ValueError("no current project")
        return Path(proj.workspace).resolve()

    result = safe_best_effort(_run, label="execute_code.workspace_cwd", default=None)
    return result if isinstance(result, Path) else None


def run_python_subprocess_safe(
    *,
    script: str,
    cwd: Path,
    timeout: int,
    env: dict[str, str],
) -> dict[str, Any] | None:
    """Return subprocess result dict, timeout dict, or ``None`` on unexpected failure."""
    try:
        proc = subprocess.run(
            ["python3", "-I", script],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[:16000],
            "stderr": (proc.stderr or "")[:4000],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "execute_code timeout", "code": "EXECUTE_CODE_TIMEOUT"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "code": "EXECUTE_CODE_ERROR"}
