"""Optional post-edit formatters (prettier/ruff) after write_file / patch."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from butler.env_parse import env_truthy, float_env

logger = logging.getLogger(__name__)

_FORMATTABLE_SUFFIXES = {
    ".py": ("ruff", ["format", "{path}"]),
    ".js": ("prettier", ["--write", "{path}"]),
    ".jsx": ("prettier", ["--write", "{path}"]),
    ".ts": ("prettier", ["--write", "{path}"]),
    ".tsx": ("prettier", ["--write", "{path}"]),
    ".json": ("prettier", ["--write", "{path}"]),
    ".md": ("prettier", ["--write", "{path}"]),
    ".css": ("prettier", ["--write", "{path}"]),
    ".yaml": ("prettier", ["--write", "{path}"]),
    ".yml": ("prettier", ["--write", "{path}"]),
}


def post_edit_format_enabled() -> bool:
    return bool(env_truthy("BUTLER_POST_EDIT_FORMAT", default=False))
def _command_available(name: str) -> bool:
    return shutil.which(name) is not None


def maybe_format_after_edit(path: Path) -> dict[str, str | bool] | None:
    """Run formatter when enabled; return info dict or None."""
    if not post_edit_format_enabled():
        return None
    suffix = path.suffix.lower()
    spec = _FORMATTABLE_SUFFIXES.get(suffix)
    if spec is None:
        return None
    tool, argv_template = spec
    if not _command_available(tool):
        return {"skipped": True, "reason": f"{tool} not in PATH"}
    path_str = str(path)
    argv = [tool] + [part.format(path=path_str) for part in argv_template[1:]]
    timeout = 30.0
    try:
        timeout = float_env("BUTLER_POST_EDIT_FORMAT_TIMEOUT", 30, min=5.0)
    except ValueError:
        pass
    try:
        proc = subprocess.run(
            argv,
            cwd=str(path.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.info("Post-edit format failed for %s: %s", path, exc)
        return {"formatted": False, "tool": tool, "error": str(exc)[:300]}
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:300]
        return {"formatted": False, "tool": tool, "error": err or f"exit {proc.returncode}"}
    return {"formatted": True, "tool": tool, "path": path_str}
