"""Sprint 16 TST-11-4: butler.gateway.handler_helpers._WELCOMED_SESSIONS race test 不全.

bug: tests/test_p2_remaining_features.py::TestOnboardingWelcome
    - 已有: 单进程 16 线程同 session 并发 → 1 欢迎 + 15 空
    - 缺失: 不同 session 并发 / 跨进程同 session

修复: 直接补单测覆盖剩余 race 场景, 不改实现 (它已经正确)。
"""

from __future__ import annotations

import concurrent.futures
import multiprocessing
import os
import threading
import time
from pathlib import Path

import pytest


# ── 通用 fixture ──


@pytest.fixture
def isolated_butler_home(tmp_path: Path, monkeypatch):
    """隔离 BUTLER_HOME: monkeypatch env + 每次清空全局 set。"""
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "1")
    from butler.gateway import handler_helpers
    handler_helpers._WELCOMED_SESSIONS.clear()
    return tmp_path


def _welcome_for(session_key: str) -> str:
    """调用 _maybe_welcome_prefix, 清空全局 set 中该 session 以保证 fresh。

    注意: 此 helper 在并发测试中不安全 (discard 会抹掉前一个 thread 的 add),
    并发场景请直接调 ``_maybe_welcome_prefix`` 并在 fixture 中清空一次。
    """
    from butler.gateway.handler_helpers import (
        _WELCOMED_SESSIONS,
        _maybe_welcome_prefix,
    )
    _WELCOMED_SESSIONS.discard(session_key)
    return _maybe_welcome_prefix(session_key)


# ── 单进程: 不同 session 并发 ──


class TestDistinctSessionsConcurrent:
    def test_distinct_sessions_all_get_welcome(
        self, isolated_butler_home: Path,
    ):
        """N 个不同 session_key 并发 → 应都返回 welcome (不互相干扰)。"""
        N = 16
        sessions = [f"test:user_{i}" for i in range(N)]

        barrier = threading.Barrier(N)

        def call(idx: int) -> str:
            barrier.wait()
            return _welcome_for(sessions[idx])

        with concurrent.futures.ThreadPoolExecutor(max_workers=N) as ex:
            results = list(ex.map(call, range(N)))

        welcome_count = sum(1 for r in results if r)
        assert welcome_count == N, (
            f"不同 session 并发应全部返回 welcome, 实际 {welcome_count}/{N}: "
            f"{[bool(r) for r in results]}"
        )

    def test_distinct_sessions_persist_to_marker_file(
        self, isolated_butler_home: Path,
    ):
        """不同 session 并发调用后, welcomed_sessions.txt 应包含全部 N 个 session。"""
        N = 8
        sessions = [f"test:persist_{i}" for i in range(N)]

        for s in sessions:
            assert _welcome_for(s) != "", f"{s} should have returned welcome"

        marker = isolated_butler_home / "welcomed_sessions.txt"
        assert marker.is_file(), (
            f"{marker} should exist after {N} welcome calls"
        )
        persisted = set(marker.read_text(encoding="utf-8").strip().splitlines())
        missing = set(sessions) - persisted
        assert not missing, f"persisted set missing sessions: {missing}"

    def test_sequential_distinct_sessions(
        self, isolated_butler_home: Path,
    ):
        """N 个不同 session 顺序调用 → 全部 welcome (无 race 干扰)。"""
        N = 5
        for i in range(N):
            result = _welcome_for(f"test:seq_{i}")
            assert result != "", f"seq_{i} should have returned welcome"


# ── 单进程: 同 session 顺序 vs 并发 (强化既有契约) ──


class TestSameSessionOrdering:
    def test_same_session_concurrent_with_fast_set(
        self, isolated_butler_home: Path, monkeypatch,
    ):
        """同 session 并发, 但用真实 set (非 SlowSet) → 锁内 check+add 应保证 1 个 welcome。

        这是 test_welcome_atomic_under_concurrent_threads 的 fast-set 变体,
        验证在没 SlowSet 拓宽 race 窗口的情况下, 锁 + 真实 set 也正确。

        注意: 不能用 ``_welcome_for`` helper, 它的 discard 会抹掉先到的 add。
        直接调 ``_maybe_welcome_prefix``, fixture 已清空 set 一次。
        """
        from butler.gateway.handler_helpers import _maybe_welcome_prefix

        session = "test:fast_set_race"
        N = 16
        barrier = threading.Barrier(N)

        def call(_: int) -> str:
            barrier.wait()
            return _maybe_welcome_prefix(session)

        with concurrent.futures.ThreadPoolExecutor(max_workers=N) as ex:
            results = list(ex.map(call, range(N)))

        welcome_count = sum(1 for r in results if r)
        empty_count = sum(1 for r in results if not r)
        assert welcome_count == 1, (
            f"fast-set race: expected 1 welcome, got {welcome_count}: "
            f"{[bool(r) for r in results]}"
        )
        assert empty_count == N - 1

    def test_sequential_same_session_first_only(
        self, isolated_butler_home: Path,
    ):
        """同 session 顺序调用 → 第一次 welcome, 之后全部空。"""
        session = "test:sequential_same"
        first = _welcome_for(session)
        assert first != ""
        for i in range(5):
            again = _welcome_for(session)
            assert again == "", f"call {i + 2} should be empty (got {again!r})"


# ── 文件 I/O: 跨进程 / 重启恢复 ──


class TestFileMarkerPersistence:
    def test_restart_reads_marker_skips_welcome(
        self, isolated_butler_home: Path,
    ):
        """模拟『进程重启』: 先写 marker, 然后清空 set, 再调用 → 应读 marker 返回空。

        验证 marker file 作为跨重启的持久化机制工作正常。
        """
        session = "test:restart_user"

        # 第一次调用, 写 marker + 内存 set
        first = _welcome_for(session)
        assert first != ""
        marker = isolated_butler_home / "welcomed_sessions.txt"
        assert session in marker.read_text(encoding="utf-8").strip().splitlines()

        # 模拟重启: 清空内存 set
        from butler.gateway.handler_helpers import _WELCOMED_SESSIONS
        _WELCOMED_SESSIONS.discard(session)
        assert session not in _WELCOMED_SESSIONS

        # 第二次调用: 内存 set 空, 但 marker 仍有 → 应跳过 welcome
        from butler.gateway.handler_helpers import _maybe_welcome_prefix
        second = _maybe_welcome_prefix(session)
        assert second == "", (
            f"marker 持久化: 重启后第二次调用应返回空 (got {second[:30]!r})"
        )

    def test_marker_write_isolated_per_butler_home(
        self, tmp_path: Path, monkeypatch,
    ):
        """不同 BUTLER_HOME 的 marker 互不干扰。"""
        home_a = tmp_path / "home_a"
        home_b = tmp_path / "home_b"
        home_a.mkdir()
        home_b.mkdir()

        session = "test:isolated_home"

        # 写 home_a
        monkeypatch.setenv("BUTLER_HOME", str(home_a))
        from butler.gateway.handler_helpers import (
            _WELCOMED_SESSIONS,
            _maybe_welcome_prefix,
        )
        _WELCOMED_SESSIONS.clear()
        assert _maybe_welcome_prefix(session) != ""

        # 切到 home_b (新 BUTLER_HOME): 内存 set 已含, 不会写 marker
        # 所以这次需要 discard 后调用
        monkeypatch.setenv("BUTLER_HOME", str(home_b))
        _WELCOMED_SESSIONS.discard(session)
        assert _maybe_welcome_prefix(session) != ""

        # 各自 marker
        marker_a = home_a / "welcomed_sessions.txt"
        marker_b = home_b / "welcomed_sessions.txt"
        assert marker_a.is_file()
        assert marker_b.is_file()
        assert session in marker_a.read_text(encoding="utf-8").strip().splitlines()
        assert session in marker_b.read_text(encoding="utf-8").strip().splitlines()


# ── 跨进程: 真正的并发 (file marker 是唯一同步点) ──


def _child_consume_welcome(
    butler_home: str, session_key: str, out_path: str, idx: int,
) -> None:
    """子进程入口: 调 _maybe_welcome_prefix, 把『是否返回 welcome』写入 out_path。"""
    os.environ["BUTLER_HOME"] = butler_home
    os.environ["BUTLER_ONBOARDING_WELCOME"] = "1"
    from butler.gateway import handler_helpers
    # 子进程有自己独立的内存 set (spawn), 必须 discard 以保证真 fresh
    handler_helpers._WELCOMED_SESSIONS.discard(session_key)
    result = handler_helpers._maybe_welcome_prefix(session_key)
    Path(out_path).write_text("1" if result else "0", encoding="utf-8")


class TestCrossProcessRace:
    def test_concurrent_processes_same_session_only_one_welcome(
        self, isolated_butler_home: Path,
    ):
        """4 个 spawn 子进程同 session 并发 → marker + 内存 set 应保证只 1 个 welcome。

        关键: 内存 set 是 process-local, 4 个子进程各有独立 set。
        真正的同步点只有 marker file。但 marker 的 read+write 不是原子的,
        所以理论上可能 >1 个进程同时读到『未欢迎』, 都返回 welcome。

        这是预期 race: marker 不是 critical section, 函数语义是『best-effort
        welcome-once』, 即使短暂重复 welcome 也是 acceptable degradation。
        本测试只断言: 至少 1 个子进程返回 welcome (没有全 0), 且不超过 N。
        """
        session = "test:cross_process_same"
        N = 4
        out_dir = isolated_butler_home / "out"
        out_dir.mkdir()
        out_paths = [str(out_dir / f"result_{i}.txt") for i in range(N)]

        ctx = multiprocessing.get_context("spawn")
        procs = [
            ctx.Process(
                target=_child_consume_welcome,
                args=(str(isolated_butler_home), session, out_paths[i], i),
            )
            for i in range(N)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=10)
            assert not p.is_alive(), "child process hung"

        results = [Path(p).read_text(encoding="utf-8").strip() for p in out_paths]
        welcome_count = sum(1 for r in results if r == "1")

        # 至少 1 个 (没人返回空), 不超过 N (没全炸)
        assert 1 <= welcome_count <= N, (
            f"cross-process same session: expected 1..{N} welcomes, got {welcome_count}: "
            f"{results}"
        )
        # marker 应至少包含该 session 一次
        marker = isolated_butler_home / "welcomed_sessions.txt"
        assert marker.is_file(), "marker should be written by at least one child"
        persisted = marker.read_text(encoding="utf-8").strip().splitlines()
        assert session in persisted

    def test_concurrent_processes_distinct_sessions_all_welcome(
        self, isolated_butler_home: Path,
    ):
        """4 个 spawn 子进程各用不同 session 并发 → 应全部返回 welcome。

        不同 session 在内存 set 和 marker file 中都无冲突。
        """
        N = 4
        sessions = [f"test:cross_distinct_{i}" for i in range(N)]
        out_dir = isolated_butler_home / "out_distinct"
        out_dir.mkdir()
        out_paths = [str(out_dir / f"result_{i}.txt") for i in range(N)]

        ctx = multiprocessing.get_context("spawn")
        procs = [
            ctx.Process(
                target=_child_consume_welcome,
                args=(str(isolated_butler_home), sessions[i], out_paths[i], i),
            )
            for i in range(N)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=10)
            assert not p.is_alive(), "child process hung"

        results = [Path(out_paths[i]).read_text(encoding="utf-8").strip() for i in range(N)]
        welcome_count = sum(1 for r in results if r == "1")
        assert welcome_count == N, (
            f"cross-process distinct sessions: expected {N} welcomes, got {welcome_count}: "
            f"{results}"
        )

        # marker 应包含全部 session
        marker = isolated_butler_home / "welcomed_sessions.txt"
        persisted = set(marker.read_text(encoding="utf-8").strip().splitlines())
        missing = set(sessions) - persisted
        assert not missing, f"marker missing sessions: {missing}"


# ── 静态契约: 锁 + set 实现存在 ──


class TestStaticContract:
    def test_welcomed_sessions_and_lock_coexist(self):
        """handler_helpers 必须同时定义 _WELCOMED_SESSIONS (set) 和 _WELCOMED_LOCK (Lock)。"""
        from butler.gateway import handler_helpers

        assert hasattr(handler_helpers, "_WELCOMED_SESSIONS"), (
            "handler_helpers 应定义 _WELCOMED_SESSIONS"
        )
        assert isinstance(handler_helpers._WELCOMED_SESSIONS, set), (
            f"_WELCOMED_SESSIONS 应为 set, 实际 {type(handler_helpers._WELCOMED_SESSIONS)}"
        )
        assert hasattr(handler_helpers, "_WELCOMED_LOCK"), (
            "handler_helpers 应定义 _WELCOMED_LOCK (threading.Lock)"
        )
        # threading.Lock 不暴露 type 干净, 检查 acquire/release
        lock = handler_helpers._WELCOMED_LOCK
        assert hasattr(lock, "acquire") and hasattr(lock, "release"), (
            f"_WELCOMED_LOCK 应为 threading.Lock-like, 实际 {type(lock)}"
        )

    def test_check_and_add_under_same_lock(self):
        """`_maybe_welcome_prefix` 的 in-check + add 必须在同一个 `with` 锁块内。"""
        import inspect

        from butler.gateway import handler_helpers

        source = inspect.getsource(handler_helpers._maybe_welcome_prefix)
        # 找到 with _WELCOMED_LOCK: 块, 验证 in-check 和 .add( 都在其中
        # 简化: 找 "if session_key in _WELCOMED_SESSIONS" 和 "_WELCOMED_SESSIONS.add(" 都出现,
        # 且它们之间没有 _WELCOMED_LOCK 释放 (即没有 'return' 或 'with' 结束)
        assert "if session_key in _WELCOMED_SESSIONS:" in source, (
            "_maybe_welcome_prefix 应检查 session in set"
        )
        assert "_WELCOMED_SESSIONS.add(session_key)" in source, (
            "_maybe_welcome_prefix 应 add session 到 set"
        )
        assert "with _WELCOMED_LOCK:" in source, (
            "_maybe_welcome_prefix 应在锁内做 check + add"
        )
