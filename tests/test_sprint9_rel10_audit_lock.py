"""Sprint 9 audit fix: REL-10 — try_acquire_lock 锁内容 PID+token; release 验证

Sprint 9 REL-10: butler/runtime/audit.py:59-93
try_acquire_lock 锁内容只写 str(time.time())，无 PID / token；
release_lock 不验证持有者 → stale takeover 后原 owner release 会
unlink 新 owner 的锁 → 实际不互斥。修复：
  - 锁内容存 PID + process-level nonce + acquire_ts
  - release_lock 读锁内容，验证 PID/nonce 匹配；不匹配 → warn + skip
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from butler.runtime import audit


def _read_lock_content(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


@pytest.mark.unit
def test_lock_file_contains_pid_and_token(tmp_path, monkeypatch):
    """try_acquire_lock 写出的锁文件应包含 PID + token。"""
    monkeypatch.setattr(audit, "_PROCESS_TOKEN", "test_nonce_abc123")
    monkeypatch.setattr(audit, "lock_path", lambda pn, jid: tmp_path / "test.lock")

    ok = audit.try_acquire_lock("proj", "job1")
    assert ok is True

    content = _read_lock_content(tmp_path / "test.lock")
    parts = content.split(":")
    assert len(parts) >= 3, f"锁内容应至少 3 段（pid:nonce:ts），实际 {content!r}"
    assert int(parts[0]) == os.getpid(), f"PID 应是当前进程 {os.getpid()}，实际 {parts[0]!r}"
    assert parts[1] == "test_nonce_abc123", (
        f"token 应是 _PROCESS_TOKEN，实际 {parts[1]!r}"
    )
    # 第三段是 acquire_ts
    float(parts[2])  # 应当可解析


@pytest.mark.unit
def test_release_lock_unlinks_when_owner_matches(tmp_path, monkeypatch):
    """当前进程持有锁时，release_lock 应 unlink。"""
    lock = tmp_path / "test.lock"
    monkeypatch.setattr(audit, "lock_path", lambda pn, jid: lock)
    monkeypatch.setattr(audit, "_PROCESS_TOKEN", "nonce_match")

    assert audit.try_acquire_lock("proj", "job1") is True
    assert lock.is_file()

    audit.release_lock("proj", "job1")
    assert not lock.is_file(), "owner 自身 release 应 unlink"


@pytest.mark.unit
def test_release_lock_does_not_unlink_other_process_lock(tmp_path, monkeypatch):
    """stale takeover 模拟：原 owner (PID_A + token_A) 被新 owner (PID_B + token_B) 替换后，
    用 PID_A+token_A 调 release_lock 不应 unlink 新 owner 的锁。
    """
    lock = tmp_path / "test.lock"
    monkeypatch.setattr(audit, "lock_path", lambda pn, jid: lock)

    # 1) 原 owner (pid=99999, token=old_token) 拿到锁
    monkeypatch.setattr(audit, "_PROCESS_TOKEN", "old_token")
    monkeypatch.setattr(os, "getpid", lambda: 99999)
    assert audit.try_acquire_lock("proj", "job1") is True
    original_content = _read_lock_content(lock)
    assert "99999" in original_content
    assert "old_token" in original_content

    # 2) 新 owner (pid=88888, token=new_token) stale takeover
    # 模拟锁已超 stale 阈值：把 mtime 改到 7300s 前
    import time as time_mod
    old_ts = time_mod.time() - 7300
    os.utime(str(lock), (old_ts, old_ts))
    monkeypatch.setattr(audit, "_PROCESS_TOKEN", "new_token")
    monkeypatch.setattr(os, "getpid", lambda: 88888)
    assert audit.try_acquire_lock("proj", "job1") is True
    new_content = _read_lock_content(lock)
    assert "88888" in new_content
    assert "new_token" in new_content

    # 3) 原 owner (pid=99999, token=old_token) 调 release_lock
    # 应 **不能** unlink 新 owner 的锁
    monkeypatch.setattr(audit, "_PROCESS_TOKEN", "old_token")
    monkeypatch.setattr(os, "getpid", lambda: 99999)
    audit.release_lock("proj", "job1")
    assert lock.is_file(), (
        "stale takeover 后，原 owner release 不应 unlink 新 owner 的锁"
    )
    assert "88888" in _read_lock_content(lock), "新 owner 的锁应完整保留"


@pytest.mark.unit
def test_release_lock_skips_unlink_on_pid_mismatch(tmp_path, monkeypatch):
    """锁内 PID 与当前进程 PID 不一致时，release_lock 应跳过 unlink。"""
    lock = tmp_path / "test.lock"
    monkeypatch.setattr(audit, "lock_path", lambda pn, jid: lock)

    # 锁文件里写一个完全不同的 PID
    lock.write_text(f"12345:other_token:{time.time()}", encoding="utf-8")

    audit.release_lock("proj", "job1")

    assert lock.is_file(), "PID 不匹配时 release 不应 unlink"


@pytest.mark.unit
def test_release_lock_skips_unlink_on_token_mismatch(tmp_path, monkeypatch):
    """锁内 nonce 与本进程 nonce 不一致时，release_lock 应跳过 unlink。"""
    lock = tmp_path / "test.lock"
    monkeypatch.setattr(audit, "lock_path", lambda pn, jid: lock)

    # 锁里写当前 PID + 错误 token
    lock.write_text(f"{os.getpid()}:different_token:{time.time()}", encoding="utf-8")
    monkeypatch.setattr(audit, "_PROCESS_TOKEN", "my_token")

    audit.release_lock("proj", "job1")

    assert lock.is_file(), "token 不匹配时 release 不应 unlink"


@pytest.mark.unit
def test_release_lock_handles_missing_lock_file(tmp_path, monkeypatch):
    """release_lock 对不存在的锁文件应是 no-op。"""
    monkeypatch.setattr(audit, "lock_path", lambda pn, jid: tmp_path / "no_such.lock")

    # 不应抛异常
    audit.release_lock("proj", "job1")


@pytest.mark.unit
def test_release_lock_handles_malformed_lock_content(tmp_path, monkeypatch):
    """release_lock 读到格式异常的锁内容应安全 no-op（不抛）。"""
    lock = tmp_path / "test.lock"
    monkeypatch.setattr(audit, "lock_path", lambda pn, jid: lock)
    lock.write_text("garbage_no_colon", encoding="utf-8")

    # 不应抛异常
    audit.release_lock("proj", "job1")
    # 也不应 unlink（无法验证持有者）
    assert lock.is_file(), "格式异常的锁不应被 release unlink"


@pytest.mark.unit
def test_process_token_is_generated_at_import_time():
    """_PROCESS_TOKEN 应在模块加载时生成（每个进程唯一）。"""
    # 至少应当是非空字符串
    assert isinstance(audit._PROCESS_TOKEN, str)
    assert len(audit._PROCESS_TOKEN) >= 8, (
        f"_PROCESS_TOKEN 长度应足够（至少 8 字符），实际 {len(audit._PROCESS_TOKEN)}"
    )
