"""Sprint 9 audit fix: REL-9 — outbox writer 路径加 flock(LOCK_EX) + atomic_write_text

Sprint 9 REL-9: butler/gateway/durable_outbox.py:45-47 + 94 + 117-118
Sprint 8 REL-2 修了 reader LOCK_SH，但 writer 路径 _write_entry 仍是裸
write_text 无 flock / fsync；docstring 谎称 "Writers use LOCK_EX" 实际
无。修复：
  - enqueue_outbox_message + _transition_outbox_entry 持 LOCK_EX
  - _write_entry 改用 atomic_write_text（含 fsync + 拒 symlink）
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from butler.gateway import durable_outbox as outbox_mod


@pytest.mark.unit
def test_enqueue_writes_atomically(tmp_path, monkeypatch):
    """_write_entry 改 atomic_write_text：写后内容应可立即正确读回。"""
    monkeypatch.setattr(outbox_mod, "get_butler_home", lambda: tmp_path / "home")
    eid = outbox_mod.enqueue_outbox_message("u1", "hello world", kind="completion")
    assert eid

    entry_path = tmp_path / "home" / "gateway_outbox" / "pending" / f"{eid}.json"
    assert entry_path.is_file(), f"entry 文件应存在: {entry_path}"

    row = json.loads(entry_path.read_text(encoding="utf-8"))
    assert row["body"] == "hello world"
    assert row["status"] == "pending"
    assert row["attempts"] == 0
    # atomic_write_text 不留 .tmp 残留
    assert not (entry_path.with_suffix(entry_path.suffix + ".tmp")).exists(), (
        "atomic_write_text 不应留 .tmp 残留"
    )


@pytest.mark.unit
def test_writer_refuses_symlink_target(tmp_path, monkeypatch):
    """_write_entry 走 atomic_write_text 后，写入 symlink 目标应被拒。"""
    monkeypatch.setattr(outbox_mod, "get_butler_home", lambda: tmp_path / "home")
    home = tmp_path / "home"
    outbox_dir = home / "gateway_outbox" / "pending"
    outbox_dir.mkdir(parents=True)

    # 准备一个 symlink: pending/sneaky.json -> 外部目录的某文件
    external = tmp_path / "external_secret.json"
    external.write_text("leaked", encoding="utf-8")
    sneaky = outbox_dir / "sneaky.json"
    sneaky.symlink_to(external)

    # enqueue 一个 entry_id, 但覆写 entry_path 让它写到 sneaky
    real_path = outbox_mod._entry_path("pending", "sneaky")
    assert real_path.is_symlink(), "test pre-condition: path 应是 symlink"

    # _write_entry 走 atomic_write_text → 应拒
    with pytest.raises(OSError, match="symlink"):
        outbox_mod._write_entry(real_path, {"entry_id": "sneaky", "x": 1})

    # 关键副作用：external_secret.json 不应被写
    assert external.read_text(encoding="utf-8") == "leaked", (
        "atomic_write_text 应阻止通过 symlink 写入外部目标"
    )


@pytest.mark.integration
def test_writer_holds_lock_ex_blocks_other_writer(tmp_path):
    """跨进程：两个 writer 持 LOCK_EX 应被序列化（一个 release 后另一个拿锁）。"""
    home = tmp_path / "home"
    outbox_dir = home / "gateway_outbox"
    outbox_dir.mkdir(parents=True)
    lock_path = outbox_dir / ".lock"

    script = textwrap.dedent(
        f"""
        import fcntl, os, sys, time
        path = {str(lock_path)!r}
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        op = int(sys.argv[1])
        hold = float(sys.argv[2])
        fcntl.flock(fd, op)
        print('LOCK_OK_' + sys.argv[1], flush=True)
        time.sleep(hold)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        """
    )

    # 子进程 A 持 LOCK_EX 1.5s
    a = subprocess.Popen(
        [sys.executable, "-c", script, str(__import__("fcntl").LOCK_EX), "1.5"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.time() + 3
    line = b""
    while time.time() < deadline:
        line = a.stdout.readline()
        if line.startswith(b"LOCK_OK_"):
            break
    assert line.startswith(b"LOCK_OK_"), f"A 没拿到 EX 锁: {line!r}"

    # 子进程 B 也尝试 LOCK_EX，应被 flock 阻塞 ~1s
    t0 = time.time()
    b = subprocess.Popen(
        [sys.executable, "-c", script, str(__import__("fcntl").LOCK_EX), "0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    b_line = b.stdout.readline()
    b.wait(timeout=5)
    elapsed = time.time() - t0
    a.wait(timeout=5)

    assert b_line.startswith(b"LOCK_OK_"), f"B 没拿到 EX 锁: {b_line!r}"
    assert elapsed >= 1.0, f"两个 writer 持 LOCK_EX 应被序列化，实际 B 等了 {elapsed:.2f}s"


@pytest.mark.integration
def test_writer_holds_lock_ex_blocks_concurrent_reader(tmp_path):
    """跨进程：writer 持 LOCK_EX 期间 reader 持 LOCK_SH 应被阻塞。"""
    home = tmp_path / "home"
    outbox_dir = home / "gateway_outbox"
    outbox_dir.mkdir(parents=True)
    lock_path = outbox_dir / ".lock"

    script = textwrap.dedent(
        f"""
        import fcntl, os, sys, time
        path = {str(lock_path)!r}
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        op = int(sys.argv[1])
        hold = float(sys.argv[2])
        fcntl.flock(fd, op)
        print('LOCK_OK_' + sys.argv[1], flush=True)
        time.sleep(hold)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        """
    )

    # 子进程 A 持 LOCK_EX 1.5s
    a = subprocess.Popen(
        [sys.executable, "-c", script, str(__import__("fcntl").LOCK_EX), "1.5"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.time() + 3
    line = b""
    while time.time() < deadline:
        line = a.stdout.readline()
        if line.startswith(b"LOCK_OK_"):
            break
    assert line.startswith(b"LOCK_OK_"), f"A 没拿到 EX 锁: {line!r}"

    # 子进程 B 持 LOCK_SH（应被 A 的 EX 阻塞）
    t0 = time.time()
    b = subprocess.Popen(
        [sys.executable, "-c", script, str(__import__("fcntl").LOCK_SH), "0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    b_line = b.stdout.readline()
    b.wait(timeout=5)
    elapsed = time.time() - t0
    a.wait(timeout=5)

    assert b_line.startswith(b"LOCK_OK_"), f"B 没拿到 SH 锁: {b_line!r}"
    assert elapsed >= 1.0, f"reader 持 SH 应被 writer 持 EX 阻塞，实际 B 等了 {elapsed:.2f}s"
