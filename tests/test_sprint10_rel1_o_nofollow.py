"""Sprint 10 REL-NEW-01: 3 处 flock 路径缺 O_NOFOLLOW → symlink bypass

Sprint 9 REL-9/10/11 修了 3 处 flock 跨进程互斥，但 `os.open` flags 都缺
`O_NOFOLLOW`。攻击者/前序进程可预置 symlink → flock 落在宿主文件，
后续 `os.replace` / `write` 改写非预期目标。Sprint 9 锁修复打折。

修复：4 个 os.open 站点加 O_NOFOLLOW（durable_outbox 2 个 + audit 1 个
+ install_pending 1 个），symlink 目标时 OSError 路径正确处理。
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest


@pytest.mark.unit
def test_durable_outbox_read_lock_uses_O_NOFOLLOW():
    """durable_outbox.py read lock（LOCK_SH）应带 O_NOFOLLOW。"""
    from butler.gateway import durable_outbox

    src = inspect.getsource(durable_outbox._outbox_read_lock)
    assert "O_NOFOLLOW" in src, (
        f"_outbox_read_lock 必须 O_NOFOLLOW\n实际源码：\n{src}"
    )


@pytest.mark.unit
def test_durable_outbox_write_lock_uses_O_NOFOLLOW():
    """durable_outbox.py write lock（LOCK_EX）应带 O_NOFOLLOW。"""
    from butler.gateway import durable_outbox

    src = inspect.getsource(durable_outbox._outbox_write_lock)
    assert "O_NOFOLLOW" in src, (
        f"_outbox_write_lock 必须 O_NOFOLLOW\n实际源码：\n{src}"
    )


@pytest.mark.unit
def test_audit_try_acquire_lock_uses_O_NOFOLLOW():
    """runtime/audit.py try_acquire_lock 应带 O_NOFOLLOW。"""
    from butler.runtime import audit

    src = inspect.getsource(audit.try_acquire_lock)
    assert "O_NOFOLLOW" in src, (
        f"try_acquire_lock 必须 O_NOFOLLOW\n实际源码：\n{src}"
    )


@pytest.mark.unit
def test_install_pending_write_lock_uses_O_NOFOLLOW():
    """registry/install_pending.py _write_lock 应带 O_NOFOLLOW。"""
    from butler.registry import install_pending

    src = inspect.getsource(install_pending._write_lock)
    assert "O_NOFOLLOW" in src, (
        f"_write_lock 必须 O_NOFOLLOW\n实际源码：\n{src}"
    )


@pytest.mark.unit
def test_durable_outbox_write_lock_rejects_symlink_target(tmp_path, monkeypatch):
    """运行时：durable_outbox lock path 是 symlink 应被拒（OSError 处理路径）。"""
    from butler.gateway import durable_outbox

    # 让 _outbox_root 落在 tmp_path
    monkeypatch.setattr(durable_outbox, "_outbox_root", lambda: tmp_path)
    # 预置 symlink 指向外部 fake "host" 目录
    external = tmp_path / "external-target"
    external.mkdir()
    symlink_path = tmp_path / ".lock"
    symlink_path.symlink_to(external)

    # 进 write_lock — 应抛 OSError（symlink bypass 拒）
    with pytest.raises(OSError):
        with durable_outbox._outbox_write_lock():
            pass

    # 外部目标不应被 flock 改写
    # 外部目录为空
    assert list(external.iterdir()) == [], (
        f"symlink 目标不应被 flock 改写：{list(external.iterdir())}"
    )


@pytest.mark.unit
def test_audit_try_acquire_lock_rejects_symlink_target(tmp_path, monkeypatch):
    """运行时：audit lock path 是 symlink 应被拒。"""
    from butler.runtime import audit

    # 让 lock_path 落在 tmp_path
    monkeypatch.setattr(audit, "lock_path", lambda p, j: tmp_path / f"{p}.{j}.lock")

    external = tmp_path / "external-audit"
    external.mkdir()
    symlink_path = tmp_path / "proj1.job1.lock"
    symlink_path.symlink_to(external)

    # try_acquire_lock 遇到 symlink 应返 False（O_NOFOLLOW 触发 OSError）
    result = audit.try_acquire_lock("proj1", "job1")
    assert result is False, f"symlink target 应拒（O_NOFOLLOW），实际 {result}"

    # 外部目标不应被改写
    assert list(external.iterdir()) == [], (
        f"symlink 目标不应被改写：{list(external.iterdir())}"
    )


@pytest.mark.unit
def test_install_pending_write_lock_rejects_symlink_target(tmp_path, monkeypatch):
    """运行时：install_pending lock path 是 symlink 应被拒。"""
    from butler.registry import install_pending as ip

    # 隔离 home
    monkeypatch.setattr(ip, "get_butler_home", lambda: tmp_path / "home")
    # 预置 symlink 指向外部
    external = tmp_path / "external-pending"
    external.mkdir()
    lock_dir = ip._pending_path().parent
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / ".pending-installs.lock"
    lock_path.symlink_to(external)

    with pytest.raises(OSError):
        with ip._write_lock():
            pass

    assert list(external.iterdir()) == [], (
        f"symlink 目标不应被改写：{list(external.iterdir())}"
    )


@pytest.mark.unit
def test_no_legacy_os_open_without_O_NOFOLLOW_in_lock_paths():
    """回归保护：4 个 lock 路径的 os.open 都不应再缺 O_NOFOLLOW。"""
    from butler.gateway import durable_outbox
    from butler.runtime import audit
    from butler.registry import install_pending

    files = [
        ("durable_outbox._outbox_read_lock", inspect.getsource(durable_outbox._outbox_read_lock)),
        ("durable_outbox._outbox_write_lock", inspect.getsource(durable_outbox._outbox_write_lock)),
        ("audit.try_acquire_lock", inspect.getsource(audit.try_acquire_lock)),
        ("install_pending._write_lock", inspect.getsource(install_pending._write_lock)),
    ]
    for name, src in files:
        # 必须在某行同时出现 os.open 与 O_NOFOLLOW
        has_open = "os.open" in src
        has_nofollow = "O_NOFOLLOW" in src
        assert has_open, f"{name} 应有 os.open"
        assert has_nofollow, f"{name} 应有 O_NOFOLLOW"
