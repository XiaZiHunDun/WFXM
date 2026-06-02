"""Tests for Sprint 13 PERF-13-1: tool embed cache 稳定 key + LRU 淘汰.

覆盖：
- 缓存键用稳定 hash（blake2b），不依赖 PYTHONHASHSEED
- 缓存命中（同一文本 → 同 key）
- LRU 淘汰：超过上限后淘汰最久未访问的项
- 缓存大小有界
"""

from __future__ import annotations

import pytest


# ── Cache key stability ────────────────────────────────────────


class TestToolEmbedCacheKeyStability:
    def test_cache_key_is_deterministic(self):
        """同一 (name, text) 多次调用必须得到相同 key（不能依赖 PYTHONHASHSEED）"""
        from butler.core.tool_selector import _tool_embed_cache_key

        k1 = _tool_embed_cache_key("read_file", "read a file from disk")
        k2 = _tool_embed_cache_key("read_file", "read a file from disk")
        assert k1 == k2
        assert isinstance(k1, str)
        assert len(k1) > 0

    def test_cache_key_differs_for_different_text(self):
        from butler.core.tool_selector import _tool_embed_cache_key

        a = _tool_embed_cache_key("read_file", "read a file from disk")
        b = _tool_embed_cache_key("read_file", "read a file from memory")
        assert a != b

    def test_cache_key_differs_for_different_name(self):
        from butler.core.tool_selector import _tool_embed_cache_key

        a = _tool_embed_cache_key("read_file", "x")
        b = _tool_embed_cache_key("write_file", "x")
        assert a != b

    def test_cache_key_does_not_use_builtin_hash(self):
        """稳定 hash 必须不依赖内置 hash()（PYTHONHASHSEED 跨进程随机）"""
        import hashlib

        from butler.core.tool_selector import _tool_embed_cache_key

        name, text = "read_file", "reads a file from disk"
        # 与实现一致：name + NUL + text
        payload = f"{name}\x00{text}".encode("utf-8")
        expected = hashlib.blake2b(payload).hexdigest()[:16]
        key = _tool_embed_cache_key(name, text)
        assert key == f"tool:{name}:{expected}"


# ── Cache size bound + LRU eviction ────────────────────────────


class TestToolEmbedCacheLRU:
    def test_cache_has_max_size_constant(self):
        from butler.core import tool_selector

        assert hasattr(tool_selector, "_TOOL_EMBED_CACHE_MAX")
        assert isinstance(tool_selector._TOOL_EMBED_CACHE_MAX, int)
        assert tool_selector._TOOL_EMBED_CACHE_MAX > 0
        assert tool_selector._TOOL_EMBED_CACHE_MAX < 10000

    def test_cache_is_ordered_dict_for_lru(self):
        from butler.core import tool_selector

        assert isinstance(tool_selector._tool_embed_cache, dict)
        # 必须是 OrderedDict（或自实现的 LRU 容器），不能是普通 dict
        # 验证 move_to_end / popitem(last=False) 可用
        assert hasattr(tool_selector._tool_embed_cache, "move_to_end")
        assert hasattr(tool_selector._tool_embed_cache, "popitem")

    def test_cache_evicts_lru_on_overflow(self):
        """调用 _semantic_score 超过上限后，最久未使用的 key 会被淘汰。"""
        from butler.core import tool_selector

        cap = tool_selector._TOOL_EMBED_CACHE_MAX
        tool_selector._tool_embed_cache.clear()

        class FakeEmbedder:
            model_id = "fake"

            def embed(self, text):
                return [0.0] * 4

        emb = FakeEmbedder()
        # 写入 cap+1 个不同的 tool
        for i in range(cap + 1):
            defn = {"function": {"name": f"tool_{i}", "description": f"desc {i}"}}
            tool_selector._semantic_score(defn, [0.0] * 4, emb)

        # cache 必须有界
        assert len(tool_selector._tool_embed_cache) == cap
        # 第一个（最久）应被淘汰，最后一个仍在
        key0 = tool_selector._tool_embed_cache_key(f"tool_0", "tool_0 desc 0")
        keyN = tool_selector._tool_embed_cache_key(f"tool_{cap}", f"tool_{cap} desc {cap}")
        assert key0 not in tool_selector._tool_embed_cache
        assert keyN in tool_selector._tool_embed_cache

    def test_lru_access_marks_recent(self):
        """访问已有 key（命中）应使其变为最近使用，不会被淘汰。"""
        from butler.core import tool_selector

        cap = tool_selector._TOOL_EMBED_CACHE_MAX
        tool_selector._tool_embed_cache.clear()

        class FakeEmbedder:
            model_id = "fake"
            call_count = 0

            def embed(self, text):
                self.call_count += 1
                return [0.0] * 4

        emb = FakeEmbedder()
        # 写入 cap 个 tool
        for i in range(cap):
            defn = {"function": {"name": f"tool_{i}", "description": f"desc {i}"}}
            tool_selector._semantic_score(defn, [0.0] * 4, emb)

        assert emb.call_count == cap

        # 再次访问 tool_0（最久），应命中（不调用 embed），并 move_to_end
        defn0 = {"function": {"name": "tool_0", "description": "desc 0"}}
        tool_selector._semantic_score(defn0, [0.0] * 4, emb)
        assert emb.call_count == cap  # 没有新调用

        # 写入新 tool_10000，触发淘汰 —— tool_0 不应被淘汰（刚被访问）
        defn_new = {"function": {"name": "tool_10000", "description": "new"}}
        tool_selector._semantic_score(defn_new, [0.0] * 4, emb)
        key0 = tool_selector._tool_embed_cache_key("tool_0", "tool_0 desc 0")
        key1 = tool_selector._tool_embed_cache_key("tool_1", "tool_1 desc 1")
        assert key0 in tool_selector._tool_embed_cache
        assert key1 not in tool_selector._tool_embed_cache


# ── Integration: _semantic_score uses stable key + bounded cache ──


class TestSemanticScoreUsesCache:
    def test_semantic_score_caches_stably(self, monkeypatch):
        """_semantic_score 缓存键应稳定（不依赖 hash()）。"""
        from butler.core import tool_selector

        calls: list[str] = []

        class FakeEmbedder:
            model_id = "fake-model-v1"

            def embed(self, text: str) -> list[float]:
                calls.append(text)
                return [0.1, 0.2, 0.3]

        defn = {
            "function": {
                "name": "read_file",
                "description": "read a file from disk",
            }
        }

        tool_selector._tool_embed_cache.clear()
        s1 = tool_selector._semantic_score(defn, [0.1, 0.2, 0.3], FakeEmbedder())
        s2 = tool_selector._semantic_score(defn, [0.1, 0.2, 0.3], FakeEmbedder())
        # 同一输入：第一次 embed 一次，第二次走缓存
        assert calls == ["read_file read a file from disk"]
        assert s1 == s2

    def test_semantic_score_does_not_grow_unbounded(self, monkeypatch):
        """重复调用 _semantic_score 不应让 cache 无限增长。"""
        from butler.core import tool_selector

        class FakeEmbedder:
            model_id = "fake-model-v1"

            def embed(self, text: str) -> list[float]:
                return [0.0] * 4

        cap = tool_selector._TOOL_EMBED_CACHE_MAX
        tool_selector._tool_embed_cache.clear()
        for i in range(cap + 50):
            defn = {
                "function": {
                    "name": f"tool_{i}",
                    "description": f"description {i}",
                }
            }
            tool_selector._semantic_score(defn, [0.0] * 4, FakeEmbedder())

        # cache 必须有界
        assert len(tool_selector._tool_embed_cache) <= cap
