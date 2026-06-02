"""Tests for Sprint 13 PERF-13-2: embedder query cache.

覆盖：
- 同一 text 不应触发第二次 embed（query 缓存命中）
- 不同 text 各自缓存
- LRU 淘汰：超过上限后淘汰最久
- HashingEmbedder 不被包装（已是无 API 开销）
- 包装后保留 model_id / dimension
- get_embedder() 返回的实例已被包装（对 API embedder）
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import pytest


# ── _CachedEmbedder unit tests ────────────────────────────────


class FakeEmbedder:
    """A non-hashing fake embedder that records embed() calls."""

    def __init__(self, dim: int = 8) -> None:
        self._dim = dim
        self._model_id = "fake-v1"
        self.calls: list[str] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        # 简单确定 embedding：字符数模 dim
        return [float(len(text) % (i + 1)) for i in range(self._dim)]


class TestCachedEmbedder:
    def test_first_call_invokes_inner(self):
        from butler.memory.embedding import _CachedEmbedder

        inner = FakeEmbedder()
        cached = _CachedEmbedder(inner, max_size=8)
        v = cached.embed("hello")
        assert v
        assert inner.calls == ["hello"]

    def test_repeat_call_uses_cache(self):
        from butler.memory.embedding import _CachedEmbedder

        inner = FakeEmbedder()
        cached = _CachedEmbedder(inner, max_size=8)
        v1 = cached.embed("hello")
        v2 = cached.embed("hello")
        assert v1 == v2
        assert inner.calls == ["hello"]  # only one embed call

    def test_different_texts_each_cached(self):
        from butler.memory.embedding import _CachedEmbedder

        inner = FakeEmbedder()
        cached = _CachedEmbedder(inner, max_size=8)
        cached.embed("a")
        cached.embed("b")
        cached.embed("a")  # cache hit
        cached.embed("b")  # cache hit
        cached.embed("c")
        assert inner.calls == ["a", "b", "c"]

    def test_lru_eviction(self):
        from butler.memory.embedding import _CachedEmbedder, _embed_cache_key

        inner = FakeEmbedder()
        cached = _CachedEmbedder(inner, max_size=2)
        # 容量 2：第 3 个写入触发淘汰最久
        cached.embed("a")
        cached.embed("b")
        cached.embed("c")  # evicts "a" (oldest)
        assert inner.calls == ["a", "b", "c"]
        assert len(cached._cache) == 2

        # "a" 应已被淘汰
        assert _embed_cache_key("a") not in cached._cache
        # "b" 和 "c" 仍在
        assert _embed_cache_key("b") in cached._cache
        assert _embed_cache_key("c") in cached._cache

        # 访问 "b" → 命中并 move_to_end
        cached.embed("b")
        assert inner.calls == ["a", "b", "c"]  # 命中，无新调用

        # 写入 "d" → 淘汰最久（现在是 "c"），"b" 仍在
        cached.embed("d")
        assert inner.calls == ["a", "b", "c", "d"]
        assert len(cached._cache) == 2
        assert _embed_cache_key("b") in cached._cache  # 仍命中
        assert _embed_cache_key("c") not in cached._cache  # 被淘汰

    def test_preserves_model_id_and_dimension(self):
        from butler.memory.embedding import _CachedEmbedder

        inner = FakeEmbedder(dim=16)
        inner._model_id = "fake-7b"
        cached = _CachedEmbedder(inner, max_size=8)
        assert cached.model_id == "fake-7b"
        assert cached.dimension == 16

    def test_empty_text_handled(self):
        from butler.memory.embedding import _CachedEmbedder

        inner = FakeEmbedder()
        cached = _CachedEmbedder(inner, max_size=8)
        v = cached.embed("")
        assert v  # non-empty
        # 空字符串也走一次 embed（key 不同就 miss）
        assert inner.calls == [""]
        cached.embed("")  # 第二次：cache hit
        assert inner.calls == [""]  # 没有第二次


# ── HashingEmbedder must NOT be wrapped ────────────────────────


class TestHashingEmbedderNotWrapped:
    def test_hashing_embedder_passthrough(self):
        """_build_embedder 对 local/hashing provider 返回原始 HashingEmbedder（不包装）。"""
        from butler.memory.embedding import _CachedEmbedder, _build_embedder, HashingEmbedder

        e = _build_embedder("local", "hashing-v1")
        assert isinstance(e, HashingEmbedder)
        assert not isinstance(e, _CachedEmbedder)

        e2 = _build_embedder("", "")
        assert isinstance(e2, HashingEmbedder)
        assert not isinstance(e2, _CachedEmbedder)


# ── _build_embedder wraps non-HashingEmbedder ─────────────────


class TestBuildEmbedderWraps:
    def test_build_embedder_wraps_non_hashing(self):
        """_build_embedder 应对非 HashingEmbedder 返回 _CachedEmbedder 包装。"""
        from butler.memory.embedding import _CachedEmbedder, _build_embedder

        class FakeNonHashing:
            @property
            def model_id(self):
                return "fake-v1"

            @property
            def dimension(self):
                return 8

            def embed(self, text):
                return [0.0] * 8

        # 通过 monkeypatch 替换 _resolve_api_embedder（openai provider 走它）
        from butler.memory import embedding as emb_mod

        original = emb_mod._resolve_api_embedder
        try:
            emb_mod._resolve_api_embedder = lambda p, m: FakeNonHashing()
            e = _build_embedder("openai", "fake-model")
        finally:
            emb_mod._resolve_api_embedder = original

        assert isinstance(e, _CachedEmbedder)
        assert e.model_id == "fake-v1"
        assert e.dimension == 8

    def test_wrapped_embedder_caches_across_calls(self):
        """_CachedEmbedder 包装后，相同 query 多次 embed 只调用一次 inner.embed。"""
        from butler.memory import embedding as emb_mod
        from butler.memory.embedding import _CachedEmbedder

        class CountingEmbedder:
            def __init__(self):
                self.calls: list[str] = []

            @property
            def model_id(self):
                return "count-v1"

            @property
            def dimension(self):
                return 4

            def embed(self, text):
                self.calls.append(text)
                return [0.0] * 4

        inner = CountingEmbedder()
        wrapped = _CachedEmbedder(inner, max_size=8)
        wrapped.embed("query A")
        wrapped.embed("query A")  # hit
        wrapped.embed("query B")
        wrapped.embed("query A")  # hit
        assert inner.calls == ["query A", "query B"]


# ── Cache key uses stable hash ────────────────────────────────


class TestCacheKeyStable:
    def test_cache_uses_stable_hash(self):
        """缓存 key 应基于稳定 hash（blake2b），不依赖内置 hash()"""
        import hashlib

        from butler.memory.embedding import _CachedEmbedder, _embed_cache_key

        text = "some query"
        expected = hashlib.blake2b(text.encode("utf-8")).hexdigest()[:16]
        assert _embed_cache_key(text) == expected

        inner = FakeEmbedder()
        cached = _CachedEmbedder(inner, max_size=8)
        cached.embed(text)
        # 内部 OrderedDict 应包含基于稳定 hash 的 key
        assert any(_embed_cache_key(text) in k for k in cached._cache.keys())
