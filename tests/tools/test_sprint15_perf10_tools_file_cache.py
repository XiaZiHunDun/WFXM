"""Tests for Sprint 15 PERF-11-10: tools 文件读取缓存.

bug: expense/contacts/habits 的 _load_all() 内 for f in glob: read_text+json.loads
每次调用都重复读+解析全部文件。单 turn 内多个工具调用 → N×M 次磁盘读。

修复：抽出 `butler/tools/_file_cache.py`，提供 read_json_cached(path)
- 按 (path, mtime_ns) 做 LRU 缓存（默认 256 条）
- mtime 变化 → 自然失效（多进程一致性）
- 命中时跳过 read_text + json.loads
- 异常（文件不存在/JSON 解析失败）返回 None，不缓存
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest


# ── helper 基本行为 ──────────────────────────────────────────


class TestReadJsonCachedBasics:
    def test_returns_parsed_dict(self, tmp_path: Path):
        from butler.tools._file_cache import read_json_cached, clear_cache

        clear_cache()
        p = tmp_path / "a.json"
        p.write_text(json.dumps({"id": "x", "v": 1}), encoding="utf-8")
        assert read_json_cached(p) == {"id": "x", "v": 1}

    def test_returns_parsed_list(self, tmp_path: Path):
        from butler.tools._file_cache import read_json_cached, clear_cache

        clear_cache()
        p = tmp_path / "b.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert read_json_cached(p) == [1, 2, 3]

    def test_returns_none_for_missing_file(self, tmp_path: Path):
        from butler.tools._file_cache import read_json_cached, clear_cache

        clear_cache()
        assert read_json_cached(tmp_path / "missing.json") is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path):
        from butler.tools._file_cache import read_json_cached, clear_cache

        clear_cache()
        p = tmp_path / "bad.json"
        p.write_text("not json{{{", encoding="utf-8")
        assert read_json_cached(p) is None

    def test_invalid_json_not_cached(self, tmp_path: Path):
        """异常情况下次仍会重试（不缓存 None）。"""
        from butler.tools._file_cache import read_json_cached, clear_cache

        clear_cache()
        p = tmp_path / "fix-me.json"
        p.write_text("not json", encoding="utf-8")
        assert read_json_cached(p) is None
        # 修复内容
        p.write_text(json.dumps({"fixed": True}), encoding="utf-8")
        # mtime 变化 → 新读
        os.utime(p, (time.time() + 1, time.time() + 1))
        assert read_json_cached(p) == {"fixed": True}


# ── 缓存命中/失效（核心 PERF 指标）─────────────────────────


class TestCacheHitAndInvalidation:
    def test_same_mtime_uses_cache(self, tmp_path: Path):
        """相同 mtime → read_text 只被调用一次。"""
        from butler.tools import _file_cache
        from butler.tools._file_cache import read_json_cached, clear_cache

        clear_cache()
        p = tmp_path / "hit.json"
        p.write_text(json.dumps({"v": 1}), encoding="utf-8")

        read_calls: list[Path] = []
        original_read = Path.read_text

        def counting_read(self, *a, **kw):
            read_calls.append(Path(self))
            return original_read(self, *a, **kw)

        with patch.object(Path, "read_text", counting_read):
            read_json_cached(p)
            read_json_cached(p)
            read_json_cached(p)

        # 只第一次真正读盘
        same_path_reads = [r for r in read_calls if r == p]
        assert len(same_path_reads) == 1, (
            f"期望 1 次 read_text，实际 {len(same_path_reads)} 次"
        )

    def test_mtime_change_invalidates_cache(self, tmp_path: Path):
        """文件被外部修改（mtime 变化）→ 重新读取。"""
        from butler.tools._file_cache import read_json_cached, clear_cache

        clear_cache()
        p = tmp_path / "mod.json"
        p.write_text(json.dumps({"v": 1}), encoding="utf-8")
        assert read_json_cached(p) == {"v": 1}

        # 模拟外部修改：内容变化 + mtime 变化
        p.write_text(json.dumps({"v": 2}), encoding="utf-8")
        os.utime(p, (time.time() + 2, time.time() + 2))

        assert read_json_cached(p) == {"v": 2}


# ── LRU 行为 ──────────────────────────────────────────────


class TestLruEviction:
    def test_evicts_oldest_when_full(self, tmp_path: Path):
        from butler.tools import _file_cache
        from butler.tools._file_cache import read_json_cached, clear_cache

        clear_cache()
        # 临时缩小上限便于测试
        original_max = _file_cache._FILE_CACHE_MAX
        _file_cache._FILE_CACHE_MAX = 3
        try:
            paths = []
            for i in range(5):
                p = tmp_path / f"f{i}.json"
                p.write_text(json.dumps({"i": i}), encoding="utf-8")
                paths.append(p)
                read_json_cached(p)

            # cache 只应留 3 个最新（f2, f3, f4）
            assert len(_file_cache._FILE_CACHE) == 3
        finally:
            _file_cache._FILE_CACHE_MAX = original_max
            clear_cache()

    def test_recent_use_avoids_eviction(self, tmp_path: Path):
        from butler.tools import _file_cache
        from butler.tools._file_cache import read_json_cached, clear_cache

        clear_cache()
        original_max = _file_cache._FILE_CACHE_MAX
        _file_cache._FILE_CACHE_MAX = 3
        try:
            paths = []
            for i in range(3):
                p = tmp_path / f"g{i}.json"
                p.write_text(json.dumps({"i": i}), encoding="utf-8")
                paths.append(p)
                read_json_cached(p)

            # 再次访问 g0（最旧）→ move_to_end
            read_json_cached(paths[0])

            # 加入 g3，应淘汰 g1（不是 g0）
            p3 = tmp_path / "g3.json"
            p3.write_text(json.dumps({"i": 3}), encoding="utf-8")
            read_json_cached(p3)

            keys = list(_file_cache._FILE_CACHE.keys())
            paths_in_cache = [k[0] for k in keys]
            assert str(paths[0]) in paths_in_cache, "g0 应保留（最近访问）"
            assert str(paths[1]) not in paths_in_cache, "g1 应被淘汰"
        finally:
            _file_cache._FILE_CACHE_MAX = original_max
            clear_cache()


# ── 集成：_file_cache 模块可用性验证 ─────────────────────
# 注：expense/contacts/habits 的 _load_all 私有 API 已在重构中移除，
# 集成测试已移除。上方基础测试覆盖了缓存核心逻辑。
