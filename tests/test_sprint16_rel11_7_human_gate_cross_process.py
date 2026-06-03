"""Sprint 16 REL-11-7: butler.human_gate.consume_injection_bypass 跨进程不原子.

bug: butler/human_gate.py:280-300
  - 使用 ``threading.Lock`` (``_gate_lock``) — 进程内有效, 跨进程失效
  - is_file() + unlink(missing_ok=True) 是 TOCTOU 模式:
    两进程可同时看到文件存在、都 ``unlink``、都返回 ``True`` (单次性失效)

修复: 改用 ``os.rename(path, consumed_path)`` — POSIX 原子, 失败方
       收到 ``FileNotFoundError`` 即知自己输了比赛, 返回 ``False``。
"""

from __future__ import annotations

import inspect
import multiprocessing as mp
import os
from pathlib import Path

import pytest


def _child_consume_with_barrier(
    butler_home: str, session_key: str, barrier, out_path: str, idx: int,
) -> None:
    """Run in a fresh subprocess. All children wait at barrier, then race-consume.

    Writes result to ``out_path`` (a unique temp file per child) — no Manager/Queue
    to avoid spawning a server process that leaks across tests.
    """
    os.environ["BUTLER_HOME"] = butler_home
    from butler.human_gate import consume_injection_bypass

    barrier.wait(timeout=10.0)  # 所有 child 同步放行后再调用
    ok = consume_injection_bypass(session_key)
    Path(out_path).write_text("1" if ok else "0", encoding="utf-8")


@pytest.fixture
def bypass_token(tmp_path: Path, monkeypatch):
    """Pre-grant an injection bypass token in isolated BUTLER_HOME."""
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    # butler.config.get_butler_home() is cached at module level; must reload
    # so the env var change is honored in each test.
    from butler.config import reload_butler_settings

    reload_butler_settings()
    from butler.human_gate import grant_injection_bypass

    grant_injection_bypass("sess-rel11-7", ttl_seconds=300.0)
    files = list((tmp_path / "human_gates").glob("inj_bypass_*.json"))
    assert len(files) == 1, f"expected 1 bypass file, got {len(files)}"
    return tmp_path, "sess-rel11-7"


# ── RED 测试 1: 多进程并发消费 (Barrier 同步), 只有一个应成功 ──


class TestConsumeCrossProcessAtomicity:
    def test_only_one_process_wins(self, bypass_token, tmp_path):
        """N 个进程通过 Barrier 同步后并发消费: 恰 1 个返回 True。

        修复前: 多个进程可能同时通过 is_file() 检查、都 unlink、都返回 True
        修复后: 仅 1 个 os.rename() 成功, 失败方收 FileNotFoundError → False
        """
        butler_home, sk = bypass_token
        N = 4
        ctx = mp.get_context("spawn")
        barrier = ctx.Barrier(N)
        out_dir = tmp_path / "results"
        out_dir.mkdir()
        out_paths = [str(out_dir / f"r{i}.txt") for i in range(N)]

        procs = [
            ctx.Process(
                target=_child_consume_with_barrier,
                args=(str(butler_home), sk, barrier, out_paths[i], i),
            )
            for i in range(N)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=15.0)
            assert not p.is_alive(), f"child {p.pid} hung"

        results = [Path(p).read_text(encoding="utf-8") == "1" for p in out_paths]
        winners = sum(1 for r in results if r)
        assert winners == 1, (
            f"consume_injection_bypass 不是跨进程原子: "
            f"{N} 个并发消费者中 {winners} 个返回 True (期望 1)。"
            f"原始结果: {results}"
        )

    def test_sequential_consume_only_first_wins(self, bypass_token):
        """单进程串行 2 次: 第 1 次 True, 第 2 次 False (消费一次后 token 应失效)。"""
        from butler.human_gate import consume_injection_bypass

        first = consume_injection_bypass("sess-rel11-7")
        second = consume_injection_bypass("sess-rel11-7")
        assert first is True, "首次消费应成功"
        assert second is False, "二次消费应失败 (token 已被消费)"


# ── RED 测试 2: 静态检查 — 实现应使用原子 rename, 不应用 is_file + unlink 模式 ──


class TestStaticContract:
    def test_consume_uses_atomic_rename(self):
        """consume_injection_bypass 必须用 os.rename() 实现跨进程原子消费。"""
        from butler.human_gate import consume_injection_bypass

        source = inspect.getsource(consume_injection_bypass)
        assert "os.rename(" in source, (
            "consume_injection_bypass 必须用 os.rename() 做跨进程原子消费; "
            "当前实现仍依赖进程内 threading.Lock + TOCTOU 模式"
        )

    def test_consume_does_not_use_toctou_unlink_pattern(self):
        """不应再出现 is_file() + unlink(missing_ok=True) 这种 TOCTOU 组合。"""
        from butler.human_gate import consume_injection_bypass

        source = inspect.getsource(consume_injection_bypass)
        assert "is_file()" not in source, (
            "consume_injection_bypass 不应使用 is_file() 预检 + unlink() 模式; "
            "这正是要修复的跨进程 TOCTOU race"
        )
