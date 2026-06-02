"""Sprint 8 audit fix: REL-2 — outbox list_pending 跨进程锁

Sprint 8 REL-2：`butler/gateway/durable_outbox.py:107-124`
list_pending_outbox 无跨进程锁；并发 mark_sent / replay 可能读到撕裂
写。修复：list_pending_outbox + outbox_counts 读时加 flock(LOCK_SH)，
确保跨进程不读到 writer 正在写一半的 entry。
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
def test_list_pending_returns_entries(tmp_path, monkeypatch):
    """主路径不被破坏：list_pending_outbox 仍返回已有 entry。"""
    monkeypatch.setattr(outbox_mod, "get_butler_home", lambda: tmp_path / "home")

    entry_id = outbox_mod.enqueue_outbox_message("u1", "hello", kind="completion")
    assert entry_id

    entries = outbox_mod.list_pending_outbox()

    assert any(e.get("entry_id") == entry_id for e in entries)
    assert any(e.get("body") == "hello" for e in entries)


@pytest.mark.unit
def test_outbox_counts_works_under_lock(tmp_path, monkeypatch):
    """outbox_counts 在锁内仍正常返回。"""
    monkeypatch.setattr(outbox_mod, "get_butler_home", lambda: tmp_path / "home")

    eid = outbox_mod.enqueue_outbox_message("u1", "hi", kind="completion")
    assert eid

    counts = outbox_mod.outbox_counts(chat_id="")

    assert counts["pending"] >= 1
    assert counts["sent"] == 0
    assert counts["failed"] == 0


@pytest.mark.unit
def test_outbox_lock_file_created(tmp_path, monkeypatch):
    """第一次读会创建 .lock 文件 — 证明锁机制被初始化。"""
    monkeypatch.setattr(outbox_mod, "get_butler_home", lambda: tmp_path / "home")
    home = tmp_path / "home"
    assert not (home / "gateway_outbox" / ".lock").exists()

    outbox_mod.list_pending_outbox()

    assert (home / "gateway_outbox" / ".lock").exists(), (
        "list_pending_outbox 应创建 .lock 文件"
    )


@pytest.mark.integration
def test_list_pending_holds_lock_under_concurrent_writer(tmp_path):
    """跨进程：reader 持 LOCK_SH 期间 writer 应被 LOCK_EX 阻塞。

    子进程 A 持 LOCK_SH（先 sleep 再 release），子进程 B 尝试 LOCK_EX
    （被 flock 阻塞），等 A 释放后 B 获得锁并完成写。
    """
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

    # 子进程 A：拿 SH，hold 1.5s
    a = subprocess.Popen(
        [sys.executable, "-c", script, str(__import__("fcntl").LOCK_SH), "1.5"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 等 A 拿到锁
    deadline = time.time() + 3
    line = b""
    while time.time() < deadline:
        line = a.stdout.readline()
        if line.startswith(b"LOCK_OK_"):
            break
    assert line.startswith(b"LOCK_OK_"), f"A 没拿到 SH 锁: {line!r}"

    # 子进程 B：拿 EX（应被 flock 阻塞 ~1s+）
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
    assert elapsed >= 1.0, f"B 应被 A 的 SH 阻塞 ~1s，实际 {elapsed:.2f}s"

    a.wait()
    b.wait()
