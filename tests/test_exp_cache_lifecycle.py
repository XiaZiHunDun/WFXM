"""R1-11 (PR-1): exp_cache 封装 + LRU + TTL + 文件锁 行为测试

审计来源: docs/reviews/project-deep-audit-2026-06-r1to8.md §R1-11
原 butler/core/exp_cache.py 179 行:
  - _MEM_CACHE / _MEM_LOADED 模块级全局 dict (line 23-24)
  - _read_entries (L80-108) / _write_entries (L111-129) 操作这些全局
  - 无 LRU 语义,无 TTL/失效时间,多进程不安全
  - 2 个调用方 (llm_retry.py:95-109, 207-217) 必须零改动

本次按审计建议重构 (8 个 RED 测试):
  1. LRU 命中后不会被淘汰 (verify touch-on-get)
  2. LRU 满容量后从头部淘汰 (verify evict-on-overflow)
  3. TTL: 过期 entry 视为 miss
  4. TTL=0 关闭 (向后兼容)
  5. 单例: get_default_backend() 返回同一实例
  6. 多线程: 并发 lookup+store 无异常,最终状态一致
  7. 模块级 _MEM_CACHE / _MEM_LOADED 已无 (encapsulated)
  8. 公开函数签名向后兼容 (3 个调用方无需改动)
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.core import exp_cache
from butler.core.exp_cache import (
    CacheBackend,
    CacheEntry,
    fingerprint_llm_request,
    get_default_backend,
    lookup_cached_response,
    reset_default_backend,
    store_cached_response,
)


# --- fixtures -----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个测试前重置 default backend (避免 state 泄漏)。"""
    reset_default_backend(None)
    yield
    reset_default_backend(None)


@pytest.fixture
def fresh_backend():
    """返回构造完毕的 CacheBackend;不走 default singleton。"""
    return CacheBackend(max_entries=10, ttl_seconds=60.0)


@pytest.fixture
def cache_path(tmp_path, monkeypatch):
    """monkeypatch _resolve_cache_path 返回 tmp 路径。"""
    p = tmp_path / "llm_cache.jsonl"
    monkeypatch.setattr(exp_cache, "_resolve_cache_path", lambda: p)
    monkeypatch.setattr(exp_cache, "_cache_enabled", lambda: True)
    monkeypatch.setenv("BUTLER_EXP_CACHE_STORE", "1")
    return p


def _write_cache_file(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# --- 1. LRU 命中后不会被淘汰 (touch-on-get) -----------------------------------

@pytest.mark.unit
def test_lru_hot_key_survives_eviction():
    """LRU: 频繁 hit 的 fp 在容量溢出时仍存活。"""
    backend = CacheBackend(max_entries=3, ttl_seconds=0)
    # 插入 3 个 entry
    backend.put("/p", "fp_a", CacheEntry(content="a", provider="", model=""))
    backend.put("/p", "fp_b", CacheEntry(content="b", provider="", model=""))
    backend.put("/p", "fp_c", CacheEntry(content="c", provider="", model=""))
    # 命中 fp_a (move to end)
    assert backend.get("/p", "fp_a") is not None
    # 插入第 4 个,evict 应该淘汰 fp_b (oldest now),不是 fp_a
    backend.put("/p", "fp_d", CacheEntry(content="d", provider="", model=""))
    assert backend.get("/p", "fp_a") is not None, "热 key (fp_a) 应保留"
    assert backend.get("/p", "fp_b") is None, "冷 key (fp_b) 应被淘汰"


# --- 2. LRU 满容量后从头部淘汰 ------------------------------------------------

@pytest.mark.unit
def test_lru_evict_oldest_on_overflow():
    """容量超出时淘汰最久未访问 (OrderedDict front = LRU)。"""
    backend = CacheBackend(max_entries=3, ttl_seconds=0)
    for i in range(3):
        backend.put("/p", f"fp_{i}", CacheEntry(content=f"c_{i}", provider="", model=""))
    # 插入第 4 个 → 淘汰 fp_0 (oldest)
    backend.put("/p", "fp_3", CacheEntry(content="c_3", provider="", model=""))
    assert backend.size("/p") == 3
    assert backend.get("/p", "fp_0") is None, "fp_0 应被淘汰"
    assert backend.get("/p", "fp_3") is not None, "fp_3 应保留"


# --- 3. TTL: 过期 entry 视为 miss ---------------------------------------------

@pytest.mark.unit
def test_ttl_expired_entry_treated_as_miss():
    """TTL=0.1s: store 后 wait 0.2s, lookup 返回 None。"""
    backend = CacheBackend(max_entries=10, ttl_seconds=0.1)
    backend.put("/p", "fp_x", CacheEntry(content="hello", provider="p", model="m"))
    # 立即 lookup 命中
    e = backend.get("/p", "fp_x")
    assert e is not None and e.content == "hello"
    # 等过期
    time.sleep(0.2)
    e2 = backend.get("/p", "fp_x")
    assert e2 is None, f"过期 entry 应视为 miss,实际 {e2!r}"


# --- 4. TTL=0 关闭 (向后兼容) ------------------------------------------------

@pytest.mark.unit
def test_ttl_zero_disables_expiration():
    """ttl_seconds=0 时 entry 永不过期。"""
    backend = CacheBackend(max_entries=10, ttl_seconds=0)
    backend.put("/p", "fp_y", CacheEntry(content="persistent", provider="", model=""))
    time.sleep(0.1)
    e = backend.get("/p", "fp_y")
    assert e is not None and e.content == "persistent"


# --- 5. 单例: get_default_backend() 返回同一实例 -----------------------------

@pytest.mark.unit
def test_default_backend_is_singleton():
    """get_default_backend() 多次调用应返回同一实例。"""
    b1 = get_default_backend()
    b2 = get_default_backend()
    assert b1 is b2, "default backend 应为单例"


@pytest.mark.unit
def test_reset_default_backend_replaces_instance():
    """reset_default_backend() 应能替换单例 (test/runtime hook)。"""
    b1 = get_default_backend()
    replacement = CacheBackend(max_entries=7, ttl_seconds=42.0)
    reset_default_backend(replacement)
    b2 = get_default_backend()
    assert b2 is replacement
    assert b2 is not b1
    assert b2.max_entries == 7
    assert b2.ttl_seconds == 42.0


# --- 6. 多线程并发安全 ---------------------------------------------------------

@pytest.mark.unit
def test_concurrent_lookup_store_thread_safe(cache_path):
    """10 线程 × 100 次 lookup+store: 无异常,最终 state 一致。"""
    # 1000 entries > default max_entries=500; 提升 capacity 避免 evict
    reset_default_backend(CacheBackend(max_entries=2000, ttl_seconds=0))
    errors: list[Exception] = []

    def worker(tid: int) -> None:
        try:
            for i in range(100):
                fp = f"fp_{tid}_{i}"
                store_cached_response(fp, f"content_{tid}_{i}", provider="p", model="m")
                r = lookup_cached_response(fp)
                if r != f"content_{tid}_{i}":
                    errors.append(AssertionError(f"线程 {tid} iter {i}: lookup 失配 {r!r}"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发出错: {errors[:3]}"
    # 1000 个 fp 全部应能 lookup
    for tid in range(10):
        for i in range(100):
            r = lookup_cached_response(f"fp_{tid}_{i}")
            assert r == f"content_{tid}_{i}"


# --- 7. 模块级 _MEM_CACHE / _MEM_LOADED 已无 ---------------------------------

@pytest.mark.unit
def test_module_globals_removed():
    """R1-11: _MEM_CACHE / _MEM_LOADED 不再是 module-level mutable state。"""
    assert not hasattr(exp_cache, "_MEM_CACHE") or not isinstance(
        getattr(exp_cache, "_MEM_CACHE", None), dict
    ), "_MEM_CACHE 不应再是 module-level dict"
    assert not hasattr(exp_cache, "_MEM_LOADED") or not isinstance(
        getattr(exp_cache, "_MEM_LOADED", None), dict
    ), "_MEM_LOADED 不应再是 module-level dict"
    # state 应封装在 CacheBackend
    backend = get_default_backend()
    assert hasattr(backend, "_path_caches")
    assert hasattr(backend, "_loaded_paths")
    assert hasattr(backend, "_lock")


# --- 8. 公开函数签名向后兼容 (3 个调用方无需改动) ---------------------------

@pytest.mark.unit
def test_public_function_signatures_unchanged(cache_path):
    """3 个公开函数签名保持不变,旧调用方 (llm_retry.py) 零改动。"""
    # fingerprint_llm_request
    fp = fingerprint_llm_request(
        provider="minimax",
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
    )
    assert isinstance(fp, str) and len(fp) == 64  # sha256 hex

    # lookup_cached_response (无命中)
    assert lookup_cached_response(fp) is None

    # store_cached_response
    store_cached_response(fp, "response text", provider="minimax", model="test-model")

    # lookup 命中
    assert lookup_cached_response(fp) == "response text"


@pytest.mark.unit
def test_public_imports_back_compat():
    """旧 import 路径仍可用 (llm_retry.py 的 3 处 import)。"""
    from butler.core.exp_cache import (  # noqa: F401
        fingerprint_llm_request,
        lookup_cached_response,
        store_cached_response,
    )


# --- 额外: env 驱动的 TTL + max_entries 配置 ---------------------------------

@pytest.mark.unit
def test_env_driven_ttl_and_max(monkeypatch, cache_path):
    """env BUTLER_EXP_CACHE_TTL_SECONDS / BUTLER_EXP_CACHE_MAX 应影响 default backend。"""
    monkeypatch.setenv("BUTLER_EXP_CACHE_TTL_SECONDS", "120")
    monkeypatch.setenv("BUTLER_EXP_CACHE_MAX", "250")
    reset_default_backend(None)
    backend = get_default_backend()
    assert backend.ttl_seconds == 120.0
    assert backend.max_entries == 250
