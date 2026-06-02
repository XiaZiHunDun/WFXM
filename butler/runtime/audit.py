"""Persist runtime run records under ~/.butler/runtime/runs/."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.config import get_butler_settings


def _runs_root() -> Path:
    root = get_butler_settings().butler_home / "runtime" / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (name or "project"))


def write_run_record(
    *,
    project_name: str,
    job_id: str,
    payload: dict[str, Any],
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _runs_root() / _slug(project_name) / job_id / f"{ts}.json"
    from butler.io.atomic_write import atomic_write_text

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def latest_run(project_name: str, job_id: str) -> dict[str, Any] | None:
    base = _runs_root() / _slug(project_name) / job_id
    if not base.is_dir():
        return None
    files = sorted(base.glob("*.json"), reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def lock_path(project_name: str, job_id: str) -> Path:
    locks = get_butler_settings().butler_home / "runtime" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    return locks / f"{_slug(project_name)}__{job_id}.lock"


def try_acquire_lock(project_name: str, job_id: str, *, stale_seconds: float = 7200) -> bool:
    path = lock_path(project_name, job_id)
    # Atomic create-or-fail: O_EXCL makes the create fail if the file
    # already exists, so two concurrent acquirers cannot both "win".
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError:
        # Lock exists — check if stale and try to take over.
        try:
            stat_result = path.stat()
        except OSError:
            return False
        age = time.time() - stat_result.st_mtime
        if age < stale_seconds:
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False
        try:
            fd = os.open(str(path), flags, 0o600)
        except FileExistsError:
            return False
        except OSError:
            return False
    except OSError:
        return False
    try:
        os.write(fd, str(time.time()).encode("utf-8"))
    finally:
        os.close(fd)
    return True


def release_lock(project_name: str, job_id: str) -> None:
    try:
        lock_path(project_name, job_id).unlink(missing_ok=True)
    except OSError:
        pass
