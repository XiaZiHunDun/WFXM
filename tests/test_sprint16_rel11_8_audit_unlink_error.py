"""Sprint 16 REL-11-8: butler.runtime.audit.release_lock 静默吞 OSError.

bug: butler/runtime/audit.py:156-159
```python
try:
    path.unlink()
except OSError:
    pass
```
所有 OSError 一律静默吞咽, 包括:
  - FileNotFoundError (race condition: 已被并发 release 删了) — OK 静默
  - PermissionError (read-only fs, 文件被 chown) — 应可见
  - IsADirectoryError (锁文件被替换为目录) — 应可见
  - OSError on parent dir gone — 应可见

修复: 显式分两路
  - FileNotFoundError: 静默 (benign race)
  - 其他 OSError: logger.warning (可见但不抛)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from butler.runtime import audit


@pytest.fixture
def locked(tmp_path: Path, monkeypatch):
    """构造 release_lock 走到 unlink 那一步的状态: 锁文件存在, 持有者 = 当前进程。"""
    lock = tmp_path / "test.lock"
    monkeypatch.setattr(audit, "lock_path", lambda pn, jid: lock)
    monkeypatch.setattr(audit, "_PROCESS_TOKEN", "owner_token")

    # 写一个匹配当前 PID + token 的锁内容
    lock.write_text(
        f"{os.getpid()}:owner_token:1234567890.0",
        encoding="utf-8",
    )
    return lock


class TestReleaseLockUnlinkErrorHandling:
    def test_filenotfound_silently_swallows(self, locked, caplog):
        """FileNotFoundError 是良性 race (已被并发删) → 应静默不抛、不告警。"""
        # 让 unlink 抛 FileNotFoundError
        real_unlink = Path.unlink

        def unlink_raises_fnf(self, *a, **kw):
            raise FileNotFoundError(2, "No such file or directory", str(self))

        from unittest.mock import patch
        with patch.object(Path, "unlink", unlink_raises_fnf):
            with caplog.at_level(logging.WARNING, logger="butler.runtime.audit"):
                # 不应抛
                audit.release_lock("proj", "job1")

        # 不应有 WARNING 日志 (FileNotFoundError 是 benign)
        warning_records = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING
            and r.name == "butler.runtime.audit"
        ]
        assert warning_records == [], (
            f"FileNotFoundError 不应产生 warning 日志: "
            f"{[r.getMessage() for r in warning_records]}"
        )

    def test_permission_error_logs_warning(self, locked, caplog):
        """PermissionError 不应被静默吞咽, 应记录 warning 让运维可见。"""
        from unittest.mock import patch

        def unlink_raises_perm(self, *a, **kw):
            raise PermissionError(13, "Permission denied", str(self))

        with patch.object(Path, "unlink", unlink_raises_perm):
            with caplog.at_level(logging.WARNING, logger="butler.runtime.audit"):
                # 不应抛
                audit.release_lock("proj", "job1")

        # 应该有 WARNING 日志
        warning_records = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING
            and r.name == "butler.runtime.audit"
        ]
        assert len(warning_records) >= 1, (
            "PermissionError 应产生 warning 日志, 实际无任何 warning"
        )
        msg = warning_records[0].getMessage()
        assert "release_lock" in msg or "unlink" in msg, (
            f"warning 应提及 release_lock/unlink, 实际: {msg!r}"
        )
        assert "Permission" in msg, f"warning 应包含异常类型信息, 实际: {msg!r}"

    def test_isadirectory_error_logs_warning(self, locked, caplog):
        """IsADirectoryError (锁文件被替换为目录) 也应记录 warning。"""
        from unittest.mock import patch

        def unlink_raises_isadir(self, *a, **kw):
            raise IsADirectoryError(21, "Is a directory", str(self))

        with patch.object(Path, "unlink", unlink_raises_isadir):
            with caplog.at_level(logging.WARNING, logger="butler.runtime.audit"):
                # 不应抛
                audit.release_lock("proj", "job1")

        warning_records = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING
            and r.name == "butler.runtime.audit"
        ]
        assert len(warning_records) >= 1, "IsADirectoryError 应产生 warning"

    def test_generic_oserror_logs_warning(self, locked, caplog):
        """通用 OSError (如设备 I/O 失败) 也应记录 warning。"""
        from unittest.mock import patch

        def unlink_raises_oserror(self, *a, **kw):
            raise OSError(5, "Input/output error", str(self))

        with patch.object(Path, "unlink", unlink_raises_oserror):
            with caplog.at_level(logging.WARNING, logger="butler.runtime.audit"):
                # 不应抛
                audit.release_lock("proj", "job1")

        warning_records = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING
            and r.name == "butler.runtime.audit"
        ]
        assert len(warning_records) >= 1, "通用 OSError 应产生 warning"

    def test_no_exception_propagates(self, locked):
        """无论 unlink 抛什么 OSError, release_lock 自身不应抛。"""
        from unittest.mock import patch

        for exc in [
            FileNotFoundError(2, "fnf", "x"),
            PermissionError(13, "perm", "x"),
            IsADirectoryError(21, "isdir", "x"),
            OSError(5, "ioerr", "x"),
        ]:
            def raise_exc(self, *a, _exc=exc, **kw):
                raise _exc

            with patch.object(Path, "unlink", raise_exc):
                # 不应抛
                audit.release_lock("proj", "job1")


# ── 回归: 正常 release 行为不变 ──────────────────────────────


class TestReleaseLockNormalBehavior:
    def test_successful_release_does_not_log(self, locked, caplog):
        """正常 release (unlink 成功) 不应产生 warning 日志。"""
        with caplog.at_level(logging.WARNING, logger="butler.runtime.audit"):
            audit.release_lock("proj", "job1")

        warning_records = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING
            and r.name == "butler.runtime.audit"
        ]
        assert warning_records == [], (
            f"正常 release 不应有 warning: "
            f"{[r.getMessage() for r in warning_records]}"
        )

    def test_successful_release_actually_unlinks(self, locked):
        """正常 release 仍应 unlink 锁文件。"""
        assert locked.is_file()
        audit.release_lock("proj", "job1")
        assert not locked.is_file()
