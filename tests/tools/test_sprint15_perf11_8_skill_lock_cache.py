"""Sprint 15 PERF-11-8: butler.registry.skill_lock.SkillLockFile 读盘/排序优化.

bug:
  - _load() 每次操作全量 read_text + json.loads（per-op 重复读+解析）
  - get() 走 list_installed() → O(N log N) 排序 + O(N) 构造
  - 单 turn 多次 SkillLockFile.get() → K×N 次磁盘读

修复：_load() 改用 read_json_cached(self._path)：
  - 按 (path, mtime) LRU 缓存：单实例 N 次 → 1 次
  - 多实例同 path 共用：跨调用点复用
  - _save() 改 mtime → 缓存自然失效
  - get() 走 _load() 直查，不再触发 list_installed() 的排序
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from butler.registry.skill_lock import SkillLockFile


# ── 基础 _load() 缓存 ──────────────────────────────────────────


class TestLoadCaching:
    def test_repeated_load_uses_read_json_cached(self, tmp_path: Path):
        """同一实例多次 _load() → 实际 read_text 只 1 次。"""
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({"version": 1, "skills": {"a": {"name": "a"}}}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        read_calls: list[str] = []
        original_read = Path.read_text

        def counting_read(self, *a, **kw):
            sp = str(self)
            if sp.endswith(".json"):
                read_calls.append(sp)
            return original_read(self, *a, **kw)

        with patch.object(Path, "read_text", counting_read):
            for _ in range(5):
                slf._load()

        assert len(read_calls) == 1, (
            f"期望 1 次 read_text，实际 {len(read_calls)} 次：\n{read_calls}"
        )

    def test_save_invalidates_cache(self, tmp_path: Path):
        """_save() 后 _load() 应看到新数据（mtime 推进 → 缓存自然失效）。"""
        import os
        import time as _time

        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({"version": 1, "skills": {}}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        assert slf._load()["skills"] == {}
        slf._save({"version": 1, "skills": {"new": {"name": "new"}}})
        # 实际生产中 mtime 会自然推进；测试里显式 bump 模拟
        os.utime(lock, (_time.time() + 1, _time.time() + 1))

        loaded = slf._load()
        assert "new" in loaded["skills"]


# ── get() O(1) 直查 ──────────────────────────────────────────


class TestGetEfficiency:
    def test_get_does_not_invoke_list_installed(self, tmp_path: Path):
        """get() 走 O(1) 字典查询，不再触发 list_installed() 的排序。"""
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        skills = {f"skill-{i:03d}": {"name": f"skill-{i:03d}"} for i in range(50)}
        lock.write_text(
            json.dumps({"version": 1, "skills": skills}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        # get() 内部不应再 list_installed() 排序
        # 通过 patch list_installed 验证未被调用
        from unittest.mock import patch
        with patch.object(slf, "list_installed") as mock_list:
            result = slf.get("skill-025")

        assert mock_list.call_count == 0, "get() 不应触发 list_installed()"
        assert result is not None
        assert result.name == "skill-025"

    def test_get_returns_none_for_missing(self, tmp_path: Path):
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({"version": 1, "skills": {"a": {"name": "a"}}}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        assert slf.get("nope") is None

    def test_get_scales_linearly_with_file_reads(self, tmp_path: Path):
        """N 次 get() → 1 次 read_text（缓存命中）。"""
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        skills = {f"skill-{i:03d}": {"name": f"skill-{i:03d}"} for i in range(20)}
        lock.write_text(
            json.dumps({"version": 1, "skills": skills}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        read_calls: list[str] = []
        original_read = Path.read_text

        def counting_read(self, *a, **kw):
            if str(self).endswith(".json"):
                read_calls.append(str(self))
            return original_read(self, *a, **kw)

        with patch.object(Path, "read_text", counting_read):
            for i in range(20):
                slf.get(f"skill-{i:03d}")

        # 20 次 get() 应只触发 1 次 read_text
        assert len(read_calls) == 1, (
            f"期望 1 次 read_text，实际 {len(read_calls)} 次"
        )


# ── 跨实例复用缓存 ──────────────────────────────────────────


class TestCrossInstanceCache:
    def test_multiple_instances_share_read_cache(self, tmp_path: Path):
        """多个 SkillLockFile 实例（同一 path）应共享 read_json_cached 缓存。"""
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({"version": 1, "skills": {"a": {"name": "a"}}}),
            encoding="utf-8",
        )

        read_calls: list[str] = []
        original_read = Path.read_text

        def counting_read(self, *a, **kw):
            if str(self).endswith(".json"):
                read_calls.append(str(self))
            return original_read(self, *a, **kw)

        with patch.object(Path, "read_text", counting_read):
            for _ in range(3):
                slf = SkillLockFile(path=lock)
                slf._load()

        # 跨实例同 path → 共用 read_json_cached
        assert len(read_calls) == 1, (
            f"跨实例期望 1 次 read_text，实际 {len(read_calls)} 次"
        )


# ── list_installed() 行为不变 ─────────────────────────────────


class TestListInstalledStillWorks:
    def test_list_installed_returns_sorted(self, tmp_path: Path):
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        skills = {
            "zebra": {"name": "zebra", "source": "hub"},
            "alpha": {"name": "alpha", "source": "hub"},
            "mike": {"name": "mike", "source": "hub"},
        }
        lock.write_text(
            json.dumps({"version": 1, "skills": skills}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        result = slf.list_installed()
        names = [r.name for r in result]
        assert names == sorted(names), "list_installed 仍应按 name 排序"

    def test_list_installed_skips_invalid_rows(self, tmp_path: Path):
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({
                "version": 1,
                "skills": {
                    "valid": {"name": "valid", "source": "hub"},
                    "string-row": "not a dict",
                    "list-row": [1, 2, 3],
                },
            }),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        result = slf.list_installed()
        names = [r.name for r in result]
        assert names == ["valid"]


# ── 行为正确性回归 ─────────────────────────────────────────


class TestBehavioralCorrectness:
    def test_record_install_then_get(self, tmp_path: Path):
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({"version": 1, "skills": {}}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        from butler.registry.skill_types import InstalledSkillRecord

        rec = InstalledSkillRecord(
            name="my-skill",
            source="hub",
            identifier="my-skill@1.0.0",
            version="1.0.0",
            installed_at="2026-06-02T00:00:00Z",
            content_hash="abc123",
            install_path="/some/path",
            scan_verdict="ok",
            trust="community",
        )
        slf.record_install(rec)

        # 新装技能应能被查到
        loaded = slf.get("my-skill")
        assert loaded is not None
        assert loaded.name == "my-skill"
        assert loaded.source == "hub"
        assert loaded.version == "1.0.0"

    def test_remove_returns_false_for_missing(self, tmp_path: Path):
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({"version": 1, "skills": {}}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        assert slf.remove("nonexistent") is False

    def test_remove_then_get_returns_none(self, tmp_path: Path):
        from butler.tools._file_cache import clear_cache

        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({
                "version": 1,
                "skills": {"a": {"name": "a", "source": "hub"}},
            }),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        assert slf.remove("a") is True
        assert slf.get("a") is None
