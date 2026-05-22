"""Execute a single runtime job (subprocess or builtin)."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from butler.runtime.builtin_handlers import run_builtin
from butler.runtime.schema import JobDef
from butler.runtime.consistency_outcome import apply_consistency_success_policy
from butler.runtime.summary_enrich import enrich_job_result

logger = logging.getLogger(__name__)


def execute_job(job: JobDef, workspace: Path) -> dict[str, Any]:
    """Run job; returns dict with success, stdout, stderr, summary, duration_seconds."""
    started = time.monotonic()
    ws = Path(workspace).expanduser().resolve()

    if job.is_builtin:
        handler = (job.handler or "").strip()
        try:
            result = run_builtin(handler, ws)
        except ValueError as exc:
            result = {
                "success": False,
                "stdout": "",
                "stderr": str(exc),
                "summary": str(exc),
            }
    else:
        if not job.command:
            result = {
                "success": False,
                "stdout": "",
                "stderr": "empty command",
                "summary": "任务未配置 command",
            }
        else:
            result = _run_subprocess(job, ws)

    result["duration_seconds"] = round(time.monotonic() - started, 2)
    if not job.is_builtin:
        result = enrich_job_result(job, ws, result, run_started_monotonic=started)
        result = apply_consistency_success_policy(job, ws, result)
    return result


def _run_subprocess(job: JobDef, workspace: Path) -> dict[str, Any]:
    from butler.runtime.workflow_version import resolve_job_command

    cmd = resolve_job_command(list(job.command), workspace)
    timeout = max(30, int(job.timeout_seconds or 900))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"timeout after {timeout}s",
            "summary": f"执行超时（{timeout}s）",
        }
    except OSError as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "summary": f"启动失败: {exc}",
        }

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    ok = proc.returncode == 0
    tail = stdout[-800:] if stdout else stderr[-800:]
    summary = tail or ("成功" if ok else f"退出码 {proc.returncode}")
    return {
        "success": ok,
        "stdout": stdout,
        "stderr": stderr,
        "summary": summary,
        "returncode": proc.returncode,
    }
