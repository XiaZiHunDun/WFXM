"""Dev verify best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.dev_engine.dev_state import VerifyResult, VerifyStatus

logger = logging.getLogger(__name__)


def load_project_dev_config_safe(workspace: Path) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        cfg_path = workspace / "project.yaml"
        if not cfg_path.is_file():
            return {}
        from butler.project.model import Project

        return dict(Project.from_yaml(cfg_path).dev or {})

    result = safe_best_effort(_run, label="verify.project_dev_config", default={})
    return result if isinstance(result, dict) else {}


def execute_verify_subprocess(
    cmd: list[str],
    workspace: Path,
    timeout: int,
    source: str,
    *,
    env: dict[str, str] | None = None,
) -> VerifyResult:
    """Run subprocess verify command; map errors to VerifyResult."""
    import os
    import subprocess
    import time

    from butler.dev_engine.diagnostics import parse_diagnostics

    t0 = time.time()
    run_env = env if env is not None else {**os.environ, "PYTHONPATH": str(workspace)}
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workspace),
            env=run_env,
        )
        elapsed = time.time() - t0
        combined = result.stdout + "\n" + result.stderr
        diagnostics = parse_diagnostics(combined, source=source)

        if result.returncode == 0:
            return VerifyResult(
                status=VerifyStatus.PASS,
                diagnostics=diagnostics,
                command=" ".join(cmd),
                elapsed_seconds=elapsed,
                exit_code=0,
            )
        tail = combined.strip()[-1500:] if combined.strip() else ""
        return VerifyResult(
            status=VerifyStatus.FAIL,
            diagnostics=diagnostics,
            command=" ".join(cmd),
            elapsed_seconds=elapsed,
            exit_code=result.returncode,
            output_tail=tail,
        )
    except subprocess.TimeoutExpired:
        return VerifyResult(
            status=VerifyStatus.TIMEOUT,
            command=" ".join(cmd),
            elapsed_seconds=time.time() - t0,
        )
    except FileNotFoundError:
        return VerifyResult(
            status=VerifyStatus.SKIP,
            command=" ".join(cmd),
            elapsed_seconds=0.0,
        )
    except Exception as exc:
        return verify_command_error_result(cmd=cmd, t0=t0, exc=exc)


def verify_command_error_result(
    *,
    cmd: list[str],
    t0: float,
    exc: BaseException,
) -> VerifyResult:
    logger.warning("Verify command failed: %s", exc)
    return VerifyResult(
        status=VerifyStatus.SKIP,
        command=" ".join(cmd),
        elapsed_seconds=time.time() - t0,
    )


def production_auto_verify_levels_safe(category: str) -> str:
    def _run() -> str:
        from butler.dev_engine.prod_delegate_bridge import production_auto_verify_levels

        return str(production_auto_verify_levels(category) or "")

    result = safe_best_effort(_run, label="verify.prod_levels", default="")
    return str(result or "")


def effective_dev_auto_verify_levels_safe(*, default: str) -> str:
    def _run() -> str:
        from butler.ops.eval_config_overrides import effective_dev_auto_verify_levels

        return str(effective_dev_auto_verify_levels(default))

    result = safe_best_effort(_run, label="verify.auto_levels", default=default)
    return str(result or default)
