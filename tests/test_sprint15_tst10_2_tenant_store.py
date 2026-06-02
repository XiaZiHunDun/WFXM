"""Tests for Sprint 15 TST-10-2: butler.tools.tenant_store.TenantStore 直测.

TenantStore 是 contacts/expense/habits 共用的基础 CRUD 模式。
之前 0 个直测，仅依赖 expense/contacts/habits 的间接覆盖。
此文件补齐每个公开方法的直测。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def store(tmp_path: Path, monkeypatch) -> Any:
    """Fresh TenantStore wired to an isolated BUTLER_HOME + tenant."""
    from butler import config as _config
    from butler.tools.tenant_store import TenantStore

    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_TENANT", "tst-test")
    _config.reload_butler_settings()
    return TenantStore("widgets")


@pytest.fixture
def gated_store(tmp_path: Path, monkeypatch) -> Any:
    from butler import config as _config
    from butler.tools.tenant_store import TenantStore

    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_TENANT", "tst-test")
    _config.reload_butler_settings()
    return TenantStore("gated", env_toggle="WIDGET_ENABLED")


# ── enabled() ──────────────────────────────────────────────


class TestEnabled:
    def test_default_no_toggle_returns_true(self, store):
        assert store.enabled() is True

    def test_toggle_unset_defaults_to_enabled(self, gated_store, monkeypatch):
        monkeypatch.delenv("WIDGET_ENABLED", raising=False)
        assert gated_store.enabled() is True

    def test_toggle_zero_disables(self, gated_store, monkeypatch):
        monkeypatch.setenv("WIDGET_ENABLED", "0")
        assert gated_store.enabled() is False

    def test_toggle_false_disables(self, gated_store, monkeypatch):
        monkeypatch.setenv("WIDGET_ENABLED", "false")
        assert gated_store.enabled() is False

    def test_toggle_no_disables(self, gated_store, monkeypatch):
        monkeypatch.setenv("WIDGET_ENABLED", "no")
        assert gated_store.enabled() is False

    def test_toggle_whitespace_stripped(self, gated_store, monkeypatch):
        monkeypatch.setenv("WIDGET_ENABLED", "  0  ")
        assert gated_store.enabled() is False

    def test_toggle_random_string_enables(self, gated_store, monkeypatch):
        """任何非 (0/false/no) 字符串都视为开启。"""
        monkeypatch.setenv("WIDGET_ENABLED", "yes")
        assert gated_store.enabled() is True
        monkeypatch.setenv("WIDGET_ENABLED", "1")
        assert gated_store.enabled() is True


# ── storage_dir() ─────────────────────────────────────────


class TestStorageDir:
    def test_returns_subdir_under_tenant_root(self, store, tmp_path: Path):
        sd = store.storage_dir()
        assert sd.name == "widgets"
        assert "tst-test" in str(sd)
        assert str(tmp_path) in str(sd)

    def test_storage_dir_not_auto_created(self, store):
        """storage_dir 只返回路径，不应自动创建目录。"""
        sd = store.storage_dir()
        # 未调 save 前应不存在（或为空）
        assert not sd.exists() or not any(sd.iterdir())


# ── save() ──────────────────────────────────────────────────


class TestSave:
    def test_save_writes_json_file(self, store):
        path = store.save({"id": "rec-1", "x": 42})
        assert path.is_file()
        assert path.name == "rec-1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"id": "rec-1", "x": 42}

    def test_save_creates_dir_if_missing(self, store):
        sd = store.storage_dir()
        assert not sd.exists()
        store.save({"id": "rec-1"})
        assert sd.is_dir()

    def test_save_overwrites_existing(self, store):
        store.save({"id": "rec-1", "v": 1})
        store.save({"id": "rec-1", "v": 2})
        data = json.loads((store.storage_dir() / "rec-1.json").read_text(encoding="utf-8"))
        assert data["v"] == 2

    def test_save_preserves_unicode(self, store):
        store.save({"id": "rec-中", "name": "测试"})
        text = (store.storage_dir() / "rec-中.json").read_text(encoding="utf-8")
        # ensure_ascii=False → 中文不应被转义
        assert "测试" in text
        assert "\\u" not in text


# ── load_all() ────────────────────────────────────────────


class TestLoadAll:
    def test_empty_when_dir_missing(self, store):
        assert store.load_all() == []

    def test_returns_all_records_sorted_by_filename(self, store):
        store.save({"id": "b"})
        store.save({"id": "a"})
        store.save({"id": "c"})
        out = store.load_all()
        ids = [r["id"] for r in out]
        # sorted by filename (a, b, c)
        assert ids == ["a", "b", "c"]

    def test_skips_invalid_json(self, store):
        store.save({"id": "good"})
        (store.storage_dir() / "bad.json").write_text("not json{{{", encoding="utf-8")
        out = store.load_all()
        assert [r["id"] for r in out] == ["good"]

    def test_skips_records_without_id(self, store):
        store.save({"id": "with-id"})
        (store.storage_dir() / "noid.json").write_text(
            json.dumps({"x": 1}), encoding="utf-8"
        )
        out = store.load_all()
        assert [r["id"] for r in out] == ["with-id"]

    def test_skips_non_dict_top_level(self, store):
        store.save({"id": "ok"})
        (store.storage_dir() / "list.json").write_text(
            json.dumps([1, 2, 3]), encoding="utf-8"
        )
        out = store.load_all()
        assert [r["id"] for r in out] == ["ok"]


class TestLoadAllSkipFiles:
    def test_skip_files_excluded_from_load_all(self, tmp_path, monkeypatch):
        from butler import config as _config
        from butler.tools.tenant_store import TenantStore

        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_TENANT", "tst")
        _config.reload_butler_settings()
        store = TenantStore("things", skip_files=frozenset({"_meta.json"}))

        store.save({"id": "x"})
        # 写一个应被跳过的特殊文件
        (store.storage_dir() / "_meta.json").write_text(
            json.dumps({"id": "meta", "x": 1}), encoding="utf-8"
        )
        out = store.load_all()
        assert [r["id"] for r in out] == ["x"]


# ── load_one() ────────────────────────────────────────────


class TestLoadOne:
    def test_load_existing(self, store):
        store.save({"id": "found", "v": 7})
        out = store.load_one("found")
        assert out == {"id": "found", "v": 7}

    def test_load_missing_returns_none(self, store):
        assert store.load_one("nonexistent") is None

    def test_load_one_id_mismatch_returns_none(self, store):
        """文件内 id 与请求 id 不一致 → 视为损坏，返回 None。"""
        store.storage_dir().mkdir(parents=True, exist_ok=True)
        (store.storage_dir() / "x.json").write_text(
            json.dumps({"id": "y", "v": 1}), encoding="utf-8"
        )
        assert store.load_one("x") is None

    def test_load_one_invalid_json_returns_none(self, store):
        store.storage_dir().mkdir(parents=True, exist_ok=True)
        (store.storage_dir() / "bad.json").write_text("{not json", encoding="utf-8")
        assert store.load_one("bad") is None


# ── delete() ──────────────────────────────────────────────


class TestDelete:
    def test_delete_existing_returns_true(self, store):
        store.save({"id": "to-delete"})
        assert store.delete("to-delete") is True
        assert not (store.storage_dir() / "to-delete.json").exists()

    def test_delete_missing_returns_false(self, store):
        assert store.delete("ghost") is False

    def test_delete_does_not_create_dir(self, store):
        assert store.delete("ghost") is False
        # 不应因 delete 调用就创建空目录
        assert not store.storage_dir().exists()


# ── count() ───────────────────────────────────────────────


class TestCount:
    def test_count_empty(self, store):
        assert store.count() == 0

    def test_count_all_records(self, store):
        for i in range(5):
            store.save({"id": f"r{i}"})
        assert store.count() == 5

    def test_count_with_predicate(self, store):
        store.save({"id": "a", "active": True})
        store.save({"id": "b", "active": False})
        store.save({"id": "c", "active": True})
        assert store.count(predicate=lambda r: r.get("active", False)) == 2

    def test_count_predicate_no_match(self, store):
        store.save({"id": "a"})
        assert store.count(predicate=lambda r: False) == 0
