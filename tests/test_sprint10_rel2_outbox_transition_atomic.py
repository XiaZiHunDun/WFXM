"""Sprint 10 REL-NEW-02: _transition_outbox_entry 读在写锁外 TOCTOU

Sprint 10 可靠性审计：gateway/durable_outbox.py:136-147
_transition_outbox_entry 读取 pending entry 在 _outbox_write_lock()
上下文之外执行 → 写时基于陈旧 read-state 决策 transition。

触发：并发 mark_delivered + 周期性 _recover_orphans → 同一条 outbox
被改写回 pending / 重复发送 / 丢失。

修复：把 read 也搬进 _outbox_write_lock() 内（与 enqueue 同款 read-
modify-write 全事务），消除 TOCTOU。Sprint 9 REL-9 已将 enqueue 的
RMW 整体进锁，_transition 是同一模式的修复遗漏。

测试核心：2 进程并发 transition 同一 entry_id 时，**只有 1 个进程**
应返回 ok=True（LOCK_EX 串行化，第 2 个进程拿到锁时 pending 已被
移到 target_state 目录，应返 False）。
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from butler.gateway import durable_outbox


@pytest.fixture(autouse=True)
def _isolated_outbox_root(tmp_path, monkeypatch):
    monkeypatch.setattr(durable_outbox, "_outbox_root", lambda: tmp_path)
    monkeypatch.setattr(durable_outbox, "durable_outbox_enabled", lambda: True)
    yield


def _seed_entry(tmp_path: Path, entry_id: str, **overrides) -> Path:
    row = {
        "entry_id": entry_id,
        "chat_id": "u1",
        "kind": "completion",
        "body": "x",
        "status": "pending",
        "attempts": 0,
        "created_at": time.time(),
    }
    row.update(overrides)
    path = durable_outbox._entry_path("pending", entry_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.unit
def test_transition_read_is_inside_write_lock_block():
    """源码验证：read_text 应在 _outbox_write_lock() 上下文内（with 块内）。

    正确顺序（修复后）：_outbox_write_lock() 出现 → read_text 出现
    错误顺序（bug）：read_text 出现 → _outbox_write_lock() 出现
    """
    src = inspect.getsource(durable_outbox._transition_outbox_entry)
    read_pos = src.find("pending.read_text(")
    lock_pos = src.find("_outbox_write_lock()")
    assert read_pos != -1, "_transition 源码应包含 pending.read_text"
    assert lock_pos != -1, "_transition 源码应含 _outbox_write_lock()"
    # 修复后：read 在 with 块内 → 出现在 lock_pos 之后
    assert read_pos > lock_pos, (
        f"pending.read_text 应在 _outbox_write_lock() 内（之后）\n"
        f"实际 read_pos={read_pos}, lock_pos={lock_pos}\n源码：\n{src}"
    )


@pytest.mark.unit
def test_transition_atomic_basic(tmp_path):
    """transition 完整 RMW 在锁内（attempts+1 + 状态切换 + move）。"""
    entry_id = "abcdef123456"
    _seed_entry(tmp_path, entry_id, attempts=0)

    result = durable_outbox._transition_outbox_entry(entry_id, target_state="delivered")
    assert result is True

    assert not durable_outbox._entry_path("pending", entry_id).is_file()
    target = durable_outbox._entry_path("delivered", entry_id)
    assert target.is_file()
    row = json.loads(target.read_text(encoding="utf-8"))
    assert row["status"] == "delivered"
    assert row["attempts"] == 1


@pytest.mark.unit
def test_transition_returns_false_for_nonexistent(tmp_path):
    """不存在的 entry_id 应返 False，不创建文件。"""
    result = durable_outbox._transition_outbox_entry("nonexistent", target_state="delivered")
    assert result is False


@pytest.mark.integration
def test_concurrent_two_processes_only_one_succeeds(tmp_path):
    """2 进程并发 transition 同一 entry：只有 1 个进程应返 True。

    修复后行为（read 在锁内）：
      - 进程 A 拿锁，pending 在 → 读 attempts=0 → 写 attempts=1
        → 移到 delivered → 释放锁。
      - 进程 B 拿锁（顺序无所谓），pending 已不在 → 返 False。
      - 最终 ok_count == 1，target.attempts == 1。

    Bug 行为（read 在锁外）：
      - 进程 A 读 attempts=0（锁外），拿锁，写 attempts=1，移走。
      - 进程 B 读 attempts=1（陈旧，但 target 已移动 → 实际读 target），
        或者读失败的 pending 副本（TOCTOU 中间态）。
      - 极端情况下两个进程都返 True（双 success 但 attempts 错乱）。
    """
    entry_id = "twoproc1"
    _seed_entry(tmp_path, entry_id, attempts=0)

    script = textwrap.dedent(
        f"""
        import os, sys
        os.environ['BUTLER_HOME'] = {str(tmp_path)!r}
        from pathlib import Path
        from butler.gateway import durable_outbox as do
        do._outbox_root = lambda: Path({str(tmp_path)!r})
        do.durable_outbox_enabled = lambda: True

        eid = {entry_id!r}
        ok = do._transition_outbox_entry(eid, target_state='delivered')
        print('CHILD_OK', ok, flush=True)
        """
    )
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=10)
        assert p.returncode == 0, f"子进程失败: {err.decode()}"
        outs.append(out.decode().strip())

    # 2 进程输出应包含 'CHILD_OK True' / 'CHILD_OK False'
    ok_count = sum(1 for o in outs if "CHILD_OK True" in o)
    false_count = sum(1 for o in outs if "CHILD_OK False" in o)
    assert ok_count == 1, (
        f"修复后只有 1 个进程应返 True，实际 ok={ok_count} false={false_count} "
        f"outputs={outs}"
    )
    assert ok_count + false_count == 2, (
        f"两进程输出应齐全：{outs}"
    )

    # 目标文件存在，attempts 应为 1
    target = tmp_path / "delivered" / f"{entry_id}.json"
    assert target.is_file()
    row = json.loads(target.read_text(encoding="utf-8"))
    assert row["attempts"] == 1, (
        f"attempts 应为 1（单次 transition 成功），实际 {row['attempts']}"
    )
    assert row["status"] == "delivered"


@pytest.mark.integration
def test_concurrent_three_processes_serialize(tmp_path):
    """3 进程并发：每进程 transition 不同 entry；LOCK_EX 串行化，全部成功。"""
    entry_ids = ["entry_a", "entry_b", "entry_c"]
    for eid in entry_ids:
        _seed_entry(tmp_path, eid, attempts=0)

    # 每进程迁一个不同 entry，验证 LOCK_EX 不互相影响（无死锁）
    script_template = textwrap.dedent(
        f"""
        import os, sys, time
        os.environ['BUTLER_HOME'] = {str(tmp_path)!r}
        from pathlib import Path
        from butler.gateway import durable_outbox as do
        do._outbox_root = lambda: Path({str(tmp_path)!r})
        do.durable_outbox_enabled = lambda: True
        eid = sys.argv[1]
        ok = do._transition_outbox_entry(eid, target_state='delivered')
        print('CHILD', eid, ok, flush=True)
        """
    )
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", script_template, eid],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for eid in entry_ids
    ]
    for p in procs:
        out, err = p.communicate(timeout=10)
        assert p.returncode == 0, f"子进程失败: {err.decode()}"
        assert "CHILD" in out.decode(), f"输出格式错: {out.decode()}"
        assert "True" in out.decode(), f"每个 entry 应被成功 transition: {out.decode()}"

    # 3 个 delivered 目录文件
    for eid in entry_ids:
        target = tmp_path / "delivered" / f"{eid}.json"
        assert target.is_file(), f"{eid} 移到 delivered 失败"
