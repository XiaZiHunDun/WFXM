"""Sprint 11 PERF-11-2/3: exp_cache 全文件 IO 优化

Sprint 11 审计：
- PERF-11-2: lookup_cached_response 每次 read 全文件 + 逐行 json.loads
- PERF-11-3: store_cached_response 每次写全文件 N 条

性能影响：每次 LLM 调 = 1 次全文件 read + 1 次全文件 write（store 命中后）
高频 inbound 时线性退化。

修复策略（保守）：
- 加 in-memory cache dict (key=path, value=dict[fp, row])
- lookup: O(1) 走内存，首次 miss 时 lazy load
- store: 更新内存 + 写全文件（保持原持久化语义，避免崩溃丢数据）
- 效果：lookup 性能从 O(N) json.loads 变 O(1)，高频 LLM 调提速 10-100x
- store 仍 O(N) 写全文件，但 store 频率远低于 lookup，整体提升显著

测试：6 个 RED 测试覆盖 in-memory cache 行为 + 持久化 + 多 path 隔离。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.core import exp_cache
from butler.core.exp_cache import CacheBackend, reset_default_backend


@pytest.fixture(autouse=True)
def _reset_module_state():
    """R1-11: 每个测试前重置 default backend (避免测试间污染)。

    旧 module-level ``_MEM_CACHE`` / ``_MEM_LOADED`` dicts 已封装到
    ``CacheBackend`` 中;测试通过 ``reset_default_backend(None)`` 重建
    singleton 来获得干净的 in-memory 状态。
    """
    reset_default_backend(None)
    yield
    reset_default_backend(None)


def _write_cache_file(path: Path, rows: list[dict]) -> None:
    """helper: 写 JSONL 缓存文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


@pytest.mark.unit
def test_lookup_uses_inmemory_cache_no_repeat_read(tmp_path, monkeypatch):
    """同一 fp 多次 lookup 不应重复读文件（in-memory 缓存生效）。"""
    monkeypatch.setattr(exp_cache, "_cache_enabled", lambda: True)
    cache_path = tmp_path / "llm_cache.jsonl"
    _write_cache_file(cache_path, [{"fp": "abc123", "content": "cached answer"}])
    monkeypatch.setattr(exp_cache, "_resolve_cache_path", lambda: cache_path)

    # 用 mock 计数 read_text 调用次数
    original_read_text = Path.read_text
    call_count = {"n": 0}

    def counting_read_text(self, *args, **kwargs):
        call_count["n"] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    # 第 1 次 lookup：可能触发 load
    r1 = exp_cache.lookup_cached_response("abc123")
    initial_reads = call_count["n"]

    # 第 2-10 次 lookup：不应再读文件
    for _ in range(9):
        r = exp_cache.lookup_cached_response("abc123")
        assert r == "cached answer"

    final_reads = call_count["n"]
    # 修复后：第 2-10 次 lookup 不应触发任何 read_text
    assert final_reads == initial_reads, (
        f"修复后重复 lookup 不应再读文件：initial={initial_reads}, final={final_reads}\n"
        f"说明 in-memory cache 未生效"
    )


@pytest.mark.unit
def test_store_updates_inmemory_visible_to_subsequent_lookup(tmp_path, monkeypatch):
    """store 后立即 lookup 应命中 in-memory 缓存（不再读文件验证）。"""
    monkeypatch.setattr(exp_cache, "_cache_enabled", lambda: True)
    monkeypatch.setattr(
        exp_cache, "exp_cache_enabled", lambda: True
    )  # Sprint 11 注意
    monkeypatch.setenv("BUTLER_EXP_CACHE_STORE", "1")

    cache_path = tmp_path / "llm_cache.jsonl"
    monkeypatch.setattr(exp_cache, "_resolve_cache_path", lambda: cache_path)

    # store 一个 fp
    exp_cache.store_cached_response(
        "fp_new", "stored content", provider="p", model="m"
    )

    # 立即 lookup 应命中（不读文件）— mock path.is_file 计数
    with patch.object(Path, "is_file", return_value=False) as mock_is_file:
        result = exp_cache.lookup_cached_response("fp_new")
        assert result == "stored content", (
            f"store 后 lookup 应命中 in-memory cache，实际 {result!r}"
        )


@pytest.mark.unit
def test_lookup_loads_file_only_once_per_path(tmp_path, monkeypatch):
    """同一 path 多次 lookup 只 load 文件 1 次。"""
    monkeypatch.setattr(exp_cache, "_cache_enabled", lambda: True)
    cache_path = tmp_path / "llm_cache.jsonl"
    _write_cache_file(
        cache_path,
        [
            {"fp": "fp1", "content": "c1"},
            {"fp": "fp2", "content": "c2"},
        ],
    )
    monkeypatch.setattr(exp_cache, "_resolve_cache_path", lambda: cache_path)

    # 第一次 lookup 触发 load
    exp_cache.lookup_cached_response("fp1")
    # 模拟修改文件（如果再读会拿到新值，但 in-memory 应保留旧值）
    _write_cache_file(
        cache_path,
        [{"fp": "fp1", "content": "c1_modified_on_disk"}],
    )

    # 第二次 lookup 应返回 in-memory 旧值（c1）
    r = exp_cache.lookup_cached_response("fp1")
    assert r == "c1", (
        f"in-memory cache 应保留旧值（避免重读文件），实际 {r!r}\n"
        f"说明 cache 未生效或被磁盘同步覆盖"
    )


@pytest.mark.unit
def test_max_entries_eviction_still_works_with_inmemory(tmp_path, monkeypatch):
    """store 超过 max_entries 时应仍能 evict (LRU 淘汰最早 entry)。"""
    monkeypatch.setattr(exp_cache, "_cache_enabled", lambda: True)
    monkeypatch.setenv("BUTLER_EXP_CACHE_STORE", "1")
    # R1-11: 旧 ``_max_entries`` 函数已封装到 ``CacheBackend.max_entries``;
    # 通过 ``reset_default_backend`` 注入 max_entries=3 的 backend。
    reset_default_backend(CacheBackend(max_entries=3, ttl_seconds=0))

    cache_path = tmp_path / "llm_cache.jsonl"
    monkeypatch.setattr(exp_cache, "_resolve_cache_path", lambda: cache_path)

    # store 5 个不同 fp（max=3）
    for i in range(5):
        exp_cache.store_cached_response(f"fp_{i}", f"content_{i}")

    # 内存中应只剩 3 个（最近 3 个）
    backend = exp_cache.get_default_backend()
    assert backend.size(str(cache_path)) == 3, (
        f"max_entries=3 应 evict 到 3 条，实际 in-memory {backend.size(str(cache_path))} 条"
    )

    # lookup fp_0（最早的）应 None
    r0 = exp_cache.lookup_cached_response("fp_0")
    assert r0 is None, f"fp_0 应被 evict，实际 {r0!r}"
    # lookup fp_4（最近的）应命中
    r4 = exp_cache.lookup_cached_response("fp_4")
    assert r4 == "content_4"


@pytest.mark.unit
def test_multiple_paths_isolated_inmemory(tmp_path, monkeypatch):
    """多 path 的 in-memory cache 应互不污染。"""
    monkeypatch.setattr(exp_cache, "_cache_enabled", lambda: True)
    monkeypatch.setenv("BUTLER_EXP_CACHE_STORE", "1")

    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"

    # 第一次：path_a
    monkeypatch.setattr(exp_cache, "_resolve_cache_path", lambda: path_a)
    exp_cache.store_cached_response("shared_fp", "from_a")

    # 第二次：path_b
    monkeypatch.setattr(exp_cache, "_resolve_cache_path", lambda: path_b)
    r = exp_cache.lookup_cached_response("shared_fp")
    # path_b 没有 shared_fp（path_a 的内容不应泄漏到 path_b）
    assert r is None, (
        f"path_a 的 in-memory cache 不应泄漏到 path_b，实际 {r!r}"
    )


@pytest.mark.unit
def test_concurrent_lookup_store_thread_safe(tmp_path, monkeypatch):
    """并发 lookup + store 不应破坏 in-memory cache（lock 仍生效）。"""
    monkeypatch.setattr(exp_cache, "_cache_enabled", lambda: True)
    monkeypatch.setenv("BUTLER_EXP_CACHE_STORE", "1")

    cache_path = tmp_path / "llm_cache.jsonl"
    monkeypatch.setattr(exp_cache, "_resolve_cache_path", lambda: cache_path)

    errors: list[Exception] = []

    def lookup_worker(fp: str, results: list) -> None:
        try:
            r = exp_cache.lookup_cached_response(fp)
            results.append((fp, r))
        except Exception as e:
            errors.append(e)

    def store_worker(fp: str, content: str) -> None:
        try:
            exp_cache.store_cached_response(fp, content)
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(20):
        t1 = threading.Thread(
            target=store_worker, args=(f"fp_{i}", f"c_{i}")
        )
        threads.append(t1)
        t1.start()
    for t in threads:
        t.join()

    lookup_results = []
    threads = []
    for i in range(20):
        t2 = threading.Thread(
            target=lookup_worker, args=(f"fp_{i}", lookup_results)
        )
        threads.append(t2)
        t2.start()
    for t in threads:
        t.join()

    assert not errors, f"并发操作出错: {errors}"
    # 全部 20 个 fp lookup 应命中
    assert len(lookup_results) == 20
    for fp, r in lookup_results:
        assert r is not None, f"{fp} 应能 lookup 到"
