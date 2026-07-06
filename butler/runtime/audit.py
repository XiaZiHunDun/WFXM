"""Persist runtime run records under ~/.butler/runtime/runs/."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from butler.config import get_butler_settings
from butler.io.safe_load import safe_load_json

logger = logging.getLogger(__name__)

# Per-process nonce for ``try_acquire_lock`` content.  Generated once at
# module import; never persisted.  ``release_lock`` compares the current
# process pid + this token against the lock file before unlinking, so a
# stale takeover (after 2h+) does not let the original owner accidentally
# unlink the new owner's lock.
_PROCESS_TOKEN: str = uuid4().hex


def _runs_root() -> Path:
    root = cast(Path, get_butler_settings().butler_home / "runtime" / "runs")
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
    # Audit R2-19: corrupt run record used to silently return None.
    # safe_load_json renames the corrupt file for forensic retention,
    # logs WARNING with exc_info, and records the event for /诊断.
    data = safe_load_json(
        files[0], default=None, kind="runtime_run_record",
    )
    return data if isinstance(data, dict) else None


def lock_path(project_name: str, job_id: str) -> Path:
    locks = cast(Path, get_butler_settings().butler_home / "runtime" / "locks")
    locks.mkdir(parents=True, exist_ok=True)
    return locks / f"{_slug(project_name)}__{job_id}.lock"


def _lock_content() -> str:
    """Build the lock file content for the current process.

    Sprint 9 REL-10: format ``pid:nonce:acquire_ts`` so ``release_lock``
    can verify the holder before unlinking.
    """
    return f"{os.getpid()}:{_PROCESS_TOKEN}:{time.time()}"


def try_acquire_lock(project_name: str, job_id: str, *, stale_seconds: float = 7200) -> bool:
    path = lock_path(project_name, job_id)
    # Atomic create-or-fail: O_EXCL makes the create fail if the file
    # already exists, so two concurrent acquirers cannot both "win".
    # Sprint 10 REL-NEW-01: O_NOFOLLOW 拒 symlink bypass。
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW
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
        os.write(fd, _lock_content().encode("utf-8"))
    finally:
        os.close(fd)
    return True


def release_lock(project_name: str, job_id: str) -> None:
    """Unlink the lock only if the current process is the recorded holder.

    Sprint 9 REL-10: 读锁内容 → 验证 pid + nonce 匹配当前进程 → 匹配
    才 unlink。不匹配 / 文件缺失 / 内容格式异常一律 no-op（warn log），
    防止 stale takeover 之后原 owner release 误删新 owner 的锁。
    """
    path = lock_path(project_name, job_id)
    try:
        content = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return
    except OSError:
        return
    parts = content.split(":", 2)
    if len(parts) < 3:
        logger.warning(
            "release_lock: 锁内容格式异常，跳过 unlink: path=%s content=%r",
            path,
            content,
        )
        return
    try:
        lock_pid = int(parts[0])
    except ValueError:
        logger.warning(
            "release_lock: 锁内容 PID 非数字，跳过 unlink: path=%s content=%r",
            path,
            content,
        )
        return
    if lock_pid != os.getpid() or parts[1] != _PROCESS_TOKEN:
        logger.warning(
            "release_lock: 锁持有者非当前进程，跳过 unlink: path=%s lock_pid=%s current_pid=%s",
            path,
            lock_pid,
            os.getpid(),
        )
        return
    try:
        path.unlink()
    except FileNotFoundError:
        # Benign race: another process or the OS already removed the lock.
        pass
    except OSError as exc:
        # PermissionError / IsADirectoryError / device I/O error etc. — 不可静默,
        # 运维需要看到为何锁未被清理, 否则可能堆积陈旧锁文件。
        logger.warning(
            "release_lock: unlink failed, 锁文件残留: path=%s err=%s",
            path,
            exc,
        )
