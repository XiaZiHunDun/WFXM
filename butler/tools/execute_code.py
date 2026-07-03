"""Restricted execute_code tool (Hermes PTC subset, default OFF)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from butler.env_parse import env_truthy

_MAX_CODE_CHARS = 8000
_DEFAULT_TIMEOUT = 30


def execute_code_enabled() -> bool:
    return env_truthy("BUTLER_EXECUTE_CODE", default=False)


def execute_code_timeout_seconds() -> int:
    try:
        from butler.env_parse import int_env

        return int_env("BUTLER_EXECUTE_CODE_TIMEOUT", _DEFAULT_TIMEOUT, min=5, max=120)
    except ValueError:
        return _DEFAULT_TIMEOUT


def execute_code_allow_network() -> bool:
    return env_truthy("BUTLER_EXECUTE_CODE_ALLOW_NETWORK", default=False)


def _workspace_cwd() -> Path:
    from butler.tools.execute_code_ops import resolve_execute_code_workspace_safe

    resolved = resolve_execute_code_workspace_safe()
    return resolved if resolved is not None else Path.cwd().resolve()


def run_execute_code(code: str, *, language: str = "python") -> dict:
    if not execute_code_enabled():
        return {
            "ok": False,
            "error": "execute_code 未启用（设置 BUTLER_EXECUTE_CODE=1 并经安全评审）",
            "code": "EXECUTE_CODE_DISABLED",
        }

    text = (code or "").strip()
    if not text:
        return {"ok": False, "error": "empty code", "code": "EXECUTE_CODE_EMPTY"}
    if len(text) > _MAX_CODE_CHARS:
        return {
            "ok": False,
            "error": f"code exceeds {_MAX_CODE_CHARS} chars",
            "code": "EXECUTE_CODE_TOO_LARGE",
        }

    lang = (language or "python").strip().lower()
    if lang not in ("python", "py"):
        return {"ok": False, "error": f"unsupported language: {language}", "code": "EXECUTE_CODE_LANG"}

    cwd = _workspace_cwd()
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if not execute_code_allow_network():
        env["HTTP_PROXY"] = ""
        env["HTTPS_PROXY"] = ""
        env["ALL_PROXY"] = ""
        env["NO_PROXY"] = "*"

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        script = fh.name

    try:
        from butler.tools.execute_code_ops import run_python_subprocess_safe

        out = run_python_subprocess_safe(
            script=script,
            cwd=cwd,
            timeout=execute_code_timeout_seconds(),
            env=env,
        )
        if out is None:
            return {"ok": False, "error": "execute_code failed", "code": "EXECUTE_CODE_ERROR"}
        return out
    finally:
        try:
            Path(script).unlink(missing_ok=True)
        except OSError:
            pass


def register_execute_code_tool(register_fn) -> None:
    if not execute_code_enabled():
        return

    def _handler(args: dict) -> str:
        out = run_execute_code(
            str(args.get("code") or ""),
            language=str(args.get("language") or "python"),
        )
        return json.dumps(out, ensure_ascii=False)

    register_fn(
        name="execute_code",
        description=(
            "Run short Python snippets in an isolated subprocess (no network by default). "
            "Requires BUTLER_EXECUTE_CODE=1."
        ),
        schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source to execute"},
                "language": {"type": "string", "default": "python"},
            },
            "required": ["code"],
        },
        handler=_handler,
        toolset="sandbox",
    )
