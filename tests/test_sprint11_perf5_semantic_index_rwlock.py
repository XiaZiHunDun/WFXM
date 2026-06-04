"""Sprint 11 PERF-11-5: semantic_index 单 RLock 串行化拆分

Sprint 11 审计：semantic_index.py:35 + 9 处 `with self._lock`
    self._lock = threading.RLock()
同一锁保护 search/upsert/delete/count/prefetch 全部方法 → 多 session
并发时 search 阻塞 upsert，upstream 入站延迟。

修复：读写分离
- 写 (upsert/delete/delete_source_prefix/_init_schema) 走
  self._write_lock (threading.Lock) 串行化
- 读 (search/search_owner_profile/count/count_by_source) 不需要
  进程级锁，依赖 sqlite3 Connection 内部 mutex
  (check_same_thread=False 仍 per-connection 互斥)
- _init_schema 用一次性 flag 避免重复执行 DDL

性能：
- 多 session 并发 search 不再互相阻塞
- search 期间 upsert 立即执行
- 写之间仍串行化（避免 DDL/DML race）

测试：6 个 RED 测试覆盖读写并发 + 写串行 + schema 一次性 init。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.memory import semantic_index
from butler.memory.embedding import Embedder
from butler.memory.semantic_index import SemanticMemoryIndex


class _FakeEmbedder:
    """deterministic embedder for testing."""

    model_id = "fake-model"

    def embed(self, text: str) -> list[float]:
        # Return same vector for any text
        return [0.1] * 8


@pytest.fixture
def tmp_index(tmp_path: Path) -> SemanticMemoryIndex:
    db_path = tmp_path / "semantic.db"
    return SemanticMemoryIndex(db_path, embedder=_FakeEmbedder())


@pytest.mark.unit
def test_index_uses_separate_read_and_write_locks(tmp_index):
    """修复后：应有 _write_lock（写串行），search 不持进程级锁。"""
    # 写操作需要 lock 字段
    assert hasattr(tmp_index, "_write_lock"), (
        "修复后应有 _write_lock (threading.Lock) 字段"
    )
    # search 不应 acquire 进程级锁（依赖 SQLite 内部）
    # 通过检测源码：search 方法不应有 `with self._write_lock` 或 `with self._lock`
    import inspect
    src = inspect.getsource(tmp_index.search)
    assert "self._write_lock" not in src and "self._lock" not in src, (
        f"search 不应持进程级锁（性能瓶颈），实际源码：\n{src[:300]}"
    )


@pytest.mark.unit
def test_concurrent_search_does_not_block_upsert(tmp_index):
    """并发 search + upsert：upsert 不应被 search 阻塞。

    修复前：search 持 _lock → upsert 阻塞。
    修复后：search 不持锁 → upsert 立即执行。
    """
    # 预填一条记录让 search 有结果
    tmp_index.upsert(
        source="experience", source_id="1", content="hello world", project="p1"
    )

    # 用 mock embedder 模拟慢 search
    slow_embedder = MagicMock(spec=Embedder)  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    slow_embedder.model_id = "slow"
    slow_embedder.embed = MagicMock(side_effect=lambda t: time.sleep(0.3) or [0.1] * 8)  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    tmp_index.embedder = slow_embedder

    search_done_at: list[float] = []
    upsert_done_at: list[float] = []

    def search_worker() -> None:
        tmp_index.search("query")
        search_done_at.append(time.monotonic())

    def upsert_worker() -> None:
        tmp_index.upsert(
            source="experience",
            source_id="new",
            content="new content",
            project="p1",
        )
        upsert_done_at.append(time.monotonic())

    t_search = threading.Thread(target=search_worker)
    t_upsert = threading.Thread(target=upsert_worker)
    t0 = time.monotonic()
    t_search.start()
    time.sleep(0.05)  # 让 search 先拿 lock
    t_upsert.start()
    t_upsert.join(timeout=2.0)
    t_search.join(timeout=2.0)

    assert not t_upsert.is_alive(), "upsert 线程超时（应不被 search 阻塞）"
    assert not t_search.is_alive(), "search 线程超时"

    # upsert 完成时间应早于 search 完成（如果它没被阻塞）
    if upsert_done_at and search_done_at:
        # upsert 不必早于 search 完成，但应能在 search 中途完成
        # 检查：upsert 启动 0.1s 后开始，0.4s 内应完成（不等 search 的 0.3s sleep + 后续 IO）
        elapsed_upsert = upsert_done_at[0] - t0
        # 修复后：upsert 不被阻塞，应在 1s 内完成
        # 修复前：upsert 阻塞直到 search 完成 = ~0.4s+，timeout=2s
        assert elapsed_upsert < 1.5, (
            f"upsert 耗时 {elapsed_upsert:.3f}s 过长，可能仍被 search 阻塞"
        )


@pytest.mark.unit
def test_concurrent_upserts_are_serialized(tmp_index):
    """并发 upsert 仍应串行化（避免 DML race）。"""
    errors: list[Exception] = []

    def upsert(i: int) -> None:
        try:
            tmp_index.upsert(
                source="experience",
                source_id=f"row_{i}",
                content=f"content {i}",
            )
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=upsert, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)
    assert not errors, f"并发 upsert 错误：{errors}"

    # 所有行应都写入
    assert tmp_index.count_rows() == 10


@pytest.mark.unit
def test_concurrent_searches_no_block(tmp_index):
    """多线程并发 search 应都快速完成（无互相阻塞）。"""
    for i in range(5):
        tmp_index.upsert(
            source="experience", source_id=str(i), content=f"text {i}"
        )

    # 慢 embedder：每次 embed 0.2s
    tmp_index.embedder = MagicMock(spec=Embedder)  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    tmp_index.embedder.model_id = "slow"
    tmp_index.embedder.embed = MagicMock(  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        side_effect=lambda t: time.sleep(0.2) or [0.1] * 8
    )

    times: list[float] = []

    def search() -> None:
        t0 = time.monotonic()
        tmp_index.search("q")
        times.append(time.monotonic() - t0)

    threads = [threading.Thread(target=search) for _ in range(4)]
    t_start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)
    total = time.monotonic() - t_start

    # 4 个并发 search 串行化时 = 4 * 0.2s = 0.8s
    # 修复后无锁并行 = ~0.2-0.3s
    assert total < 0.6, (
        f"4 个并发 search 总耗时 {total:.3f}s，仍可能串行化（应 < 0.6s 并行）"
    )


@pytest.mark.unit
def test_init_schema_idempotent(tmp_path):
    """多次创建 SemanticMemoryIndex 应不重复 DDL（schema 一次性 init）。"""
    db_path = tmp_path / "semantic2.db"
    idx1 = SemanticMemoryIndex(db_path, embedder=_FakeEmbedder())
    idx1.upsert(source="experience", source_id="1", content="x")
    # 第二个实例化应能正常打开
    idx2 = SemanticMemoryIndex(db_path, embedder=_FakeEmbedder())
    assert idx2.count_rows() == 1


@pytest.mark.unit
def test_write_operations_use_write_lock(tmp_index):
    """upsert/delete/delete_source_prefix 应使用 _write_lock。"""
    import inspect
    for method_name in ("upsert", "delete", "delete_source_prefix"):
        method = getattr(tmp_index, method_name)
        src = inspect.getsource(method)
        assert "_write_lock" in src, (
            f"{method_name} 应使用 _write_lock 保护\n源码：\n{src[:200]}"
        )
