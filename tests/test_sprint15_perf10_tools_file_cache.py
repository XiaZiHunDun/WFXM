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


# ── 集成：expense._load_all 复用缓存 ───────────────────────


def _reset_butler_home(monkeypatch, tmp_path: Path) -> None:
    """重置 BUTLER_HOME 并强制 reload settings 单例（突破缓存）。"""
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_TENANT", "test")
    from butler import config as _config

    _config.reload_butler_settings()


class TestExpenseLoadAllUsesCache:
    def test_repeated_load_all_only_reads_each_file_once(
        self, tmp_path: Path, monkeypatch
    ):
        """expense._load_all() 调用 N 次，每个 JSON 文件只 read_text 一次。"""
        from butler.tools import _file_cache
        from butler.tools._file_cache import clear_cache

        clear_cache()
        _reset_butler_home(monkeypatch, tmp_path)
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "1")

        # 必须在 env 设好后再 import，避免 module-level _store 锁定旧路径
        import importlib

        from butler.tools import expense as expense_mod
        importlib.reload(expense_mod)

        # 写 5 个 expense JSON
        d = expense_mod._expenses_dir()
        d.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            (d / f"e{i}.json").write_text(
                json.dumps({"id": f"e{i}", "amount": float(i), "direction": "expense"}),
                encoding="utf-8",
            )

        read_calls: list[str] = []
        original_read = Path.read_text

        def counting_read(self, *a, **kw):
            sp = str(self)
            if sp.endswith(".json") and "expenses" in sp:
                read_calls.append(sp)
            return original_read(self, *a, **kw)

        with patch.object(Path, "read_text", counting_read):
            for _ in range(3):
                records = expense_mod._load_all()
                assert len(records) == 5

        # 5 个文件，每个只读 1 次（共 5 次），而不是 3×5=15 次
        assert len(read_calls) == 5, (
            f"期望 5 次 read_text（每文件 1 次），实际 {len(read_calls)} 次：\n"
            f"{read_calls}"
        )


# ── 集成：contacts._load_all 复用缓存 ──────────────────────


class TestContactsLoadAllUsesCache:
    def test_repeated_load_all_only_reads_each_file_once(
        self, tmp_path: Path, monkeypatch
    ):
        from butler.tools._file_cache import clear_cache

        clear_cache()
        _reset_butler_home(monkeypatch, tmp_path)
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "1")

        import importlib

        from butler.tools import contacts as contacts_mod
        importlib.reload(contacts_mod)

        d = contacts_mod._contacts_dir()
        d.mkdir(parents=True, exist_ok=True)
        for i in range(4):
            (d / f"c{i}.json").write_text(
                json.dumps({"id": f"c{i}", "name": f"name{i}"}),
                encoding="utf-8",
            )

        read_calls: list[str] = []
        original_read = Path.read_text

        def counting_read(self, *a, **kw):
            sp = str(self)
            if sp.endswith(".json") and "contacts" in sp:
                read_calls.append(sp)
            return original_read(self, *a, **kw)

        with patch.object(Path, "read_text", counting_read):
            for _ in range(3):
                records = contacts_mod._load_all()
                assert len(records) == 4

        assert len(read_calls) == 4, (
            f"期望 4 次 read_text，实际 {len(read_calls)} 次"
        )


# ── 集成：habits._load_all_habits 复用缓存 ─────────────────


class TestHabitsLoadAllUsesCache:
    def test_repeated_load_all_only_reads_each_file_once(
        self, tmp_path: Path, monkeypatch
    ):
        from butler.tools._file_cache import clear_cache

        clear_cache()
        _reset_butler_home(monkeypatch, tmp_path)
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "1")

        import importlib

        from butler.tools import habits as habits_mod
        importlib.reload(habits_mod)

        d = habits_mod._habits_dir()
        d.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            (d / f"h{i}.json").write_text(
                json.dumps({"id": f"h{i}", "name": f"habit{i}"}),
                encoding="utf-8",
            )

        read_calls: list[str] = []
        original_read = Path.read_text

        def counting_read(self, *a, **kw):
            sp = str(self)
            if sp.endswith(".json") and "habits" in sp:
                read_calls.append(sp)
            return original_read(self, *a, **kw)

        with patch.object(Path, "read_text", counting_read):
            for _ in range(3):
                records = habits_mod._load_all_habits()
                assert len(records) == 3

        assert len(read_calls) == 3, (
            f"期望 3 次 read_text，实际 {len(read_calls)} 次"
        )


# ── 写入后立即读取：mtime 应反映新内容 ──────────────────


class TestWriteThenReadConsistency:
    def test_save_then_load_returns_new_record(self, tmp_path: Path, monkeypatch):
        """新增 expense 后立即 list → 应包含新记录（mtime 失效有效）。"""
        from butler.tools._file_cache import clear_cache

        clear_cache()
        _reset_butler_home(monkeypatch, tmp_path)
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "1")

        import importlib

        from butler.tools import expense as expense_mod
        importlib.reload(expense_mod)

        # 先 load（空目录）
        assert expense_mod._load_all() == []

        # 新建一个记录
        expense_mod._save_record({
            "id": "new-1",
            "amount": 42.0,
            "direction": "expense",
            "category": "food",
            "description": "test",
            "date": "2026-06-02",
            "created_at": time.time(),
        })

        # 再次 load — 应立刻看到（dir glob 拿到新文件，新文件 mtime 不在 cache）
        records = expense_mod._load_all()
        assert len(records) == 1
        assert records[0]["id"] == "new-1"
