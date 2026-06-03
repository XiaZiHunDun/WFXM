"""Sprint 10 backlog TST-10-2: butler.tools.tenant_store.TenantStore 0 直测.

bug: butler/tools/tenant_store.py TenantStore 是 memo/contacts/expense/habits
的共享基类, 但 audit 标记 0 直测 (仅间接通过子类测)。

修复: 补 TenantStore 全 API 单元测试, 不改实现 (实现正确, 只是没测)。
覆盖:
- enabled: 默认 True, env_toggle 解析 (0/false/no 关闭), 空白处理
- storage_dir: 默认 tenant, BUTLER_TENANT 切换, subdir 拼接到 tenant root
- save: 写 JSON 到 <dir>/<id>.json, 自动创建 dir
- load_all: 排序、跳过 skip_files、JSON 解析失败、缺 id 字段、非 dict
- load_one: 命中、缺失、id 不匹配、JSON 错误
- delete: 命中返 True, 缺失返 False
- count: 全量、按 predicate 过滤
- 静态契约: 导出符号
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from butler.tools.tenant_store import TenantStore


# ── 公共 fixture: 隔离 BUTLER_HOME / BUTLER_TENANT ──


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """将 BUTLER_HOME 指向 tmp_path, 默认 tenant。
    必须 reload_butler_settings(), 因为 get_butler_settings() 是单例缓存。"""
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.delenv("BUTLER_TENANT", raising=False)
    from butler import config
    config.reload_butler_settings()
    yield tmp_path
    # 还原: 触发下次 import 重新从 env 读
    config.reload_butler_settings()


@pytest.fixture
def custom_tenant(isolated_home, monkeypatch):
    """BUTLER_TENANT=acme → 切到 <home>/tenants/acme/。"""
    monkeypatch.setenv("BUTLER_TENANT", "acme")
    from butler import config
    config.reload_butler_settings()
    return isolated_home


# ── enabled ──


class TestEnabled:
    def test_no_env_toggle_always_enabled(self):
        s = TenantStore("memo")
        assert s.enabled() is True

    def test_env_toggle_default_1_enabled(self, monkeypatch):
        monkeypatch.delenv("MY_TOOL", raising=False)
        s = TenantStore("memo", env_toggle="MY_TOOL")
        assert s.enabled() is True

    def test_env_toggle_0_disabled(self, monkeypatch):
        monkeypatch.setenv("MY_TOOL", "0")
        s = TenantStore("memo", env_toggle="MY_TOOL")
        assert s.enabled() is False

    @pytest.mark.parametrize("val", ["0", "false", "no", " 0 ", " false "])
    def test_env_toggle_falsy_values_disabled(self, monkeypatch, val):
        """小写 'false'/'no' + '0' 是禁用值 (大小写敏感, 源码不 .lower())。"""
        monkeypatch.setenv("MY_TOOL", val)
        s = TenantStore("memo", env_toggle="MY_TOOL")
        assert s.enabled() is False, f"value {val!r} 应判定为 disabled"

    def test_env_toggle_truthy_enabled(self, monkeypatch):
        monkeypatch.setenv("MY_TOOL", "1")
        s = TenantStore("memo", env_toggle="MY_TOOL")
        assert s.enabled() is True

    def test_env_toggle_with_surrounding_whitespace(self, monkeypatch):
        monkeypatch.setenv("MY_TOOL", "  1  ")
        s = TenantStore("memo", env_toggle="MY_TOOL")
        assert s.enabled() is True


# ── storage_dir ──


class TestStorageDir:
    def test_default_tenant(self, isolated_home):
        s = TenantStore("memo")
        d = s.storage_dir()
        # tenant_root(butler_home, "default") = butler_home/tenants/default/
        assert d == isolated_home / "tenants" / "default" / "memo"

    def test_custom_tenant(self, custom_tenant):
        s = TenantStore("memo")
        d = s.storage_dir()
        assert d == custom_tenant / "tenants" / "acme" / "memo"

    def test_subdir_propagated(self, isolated_home):
        s = TenantStore("contacts")
        d = s.storage_dir()
        assert d.name == "contacts"

    def test_storage_dir_does_not_create_dir(self, isolated_home):
        """storage_dir() 只计算路径, 不创建目录。"""
        s = TenantStore("nonexistent")
        d = s.storage_dir()
        assert not d.exists()


# ── save ──


class TestSave:
    def test_writes_json_to_id_named_file(self, isolated_home):
        s = TenantStore("memo")
        path = s.save({"id": "rec-1", "text": "hello"})
        assert path.exists()
        assert path.name == "rec-1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"id": "rec-1", "text": "hello"}

    def test_creates_storage_dir(self, isolated_home):
        s = TenantStore("memo")
        assert not (isolated_home / "tenants" / "default" / "memo").exists()
        s.save({"id": "x"})
        assert (isolated_home / "tenants" / "default" / "memo").is_dir()

    def test_ensure_ascii_false_preserves_unicode(self, isolated_home):
        """中文/emoji 不应被 \\uXXXX 转义。"""
        s = TenantStore("memo")
        path = s.save({"id": "zh", "text": "中文 🌟"})
        raw = path.read_text(encoding="utf-8")
        assert "中文" in raw
        assert "🌟" in raw
        assert "\\u" not in raw

    def test_indent_2(self, isolated_home):
        """save 写出来应有 2 空格 indent (indent=2)。"""
        s = TenantStore("memo")
        path = s.save({"id": "x", "a": 1})
        raw = path.read_text(encoding="utf-8")
        # json.dumps(indent=2) 输出形如 '{\n  "a": 1,\n  ...'
        assert '\n  "' in raw

    def test_overwrite_existing_record(self, isolated_home):
        """save 覆盖已有 record (id 相同时)。"""
        s = TenantStore("memo")
        s.save({"id": "x", "v": 1})
        s.save({"id": "x", "v": 2})
        records = s.load_all()
        assert len(records) == 1
        assert records[0]["v"] == 2


# ── load_all ──


class TestLoadAll:
    def test_empty_dir_returns_empty_list(self, isolated_home):
        s = TenantStore("memo")
        assert s.load_all() == []

    def test_missing_dir_returns_empty_list(self, isolated_home):
        s = TenantStore("never_created")
        # 不存在的 dir → 返 []
        assert s.load_all() == []

    def test_loads_multiple_records_sorted_by_filename(self, isolated_home):
        s = TenantStore("memo")
        (isolated_home / "tenants" / "default" / "memo").mkdir(parents=True, exist_ok=True)
        for i in (3, 1, 2):
            s.save({"id": f"r{i}", "v": i})
        records = s.load_all()
        # sorted(d.glob("*.json")) → 字典序
        assert [r["id"] for r in records] == ["r1", "r2", "r3"]

    def test_skips_skip_files(self, isolated_home):
        s = TenantStore("memo", skip_files=frozenset({"_index.json"}))
        (isolated_home / "tenants" / "default" / "memo").mkdir(parents=True, exist_ok=True)
        (isolated_home / "tenants" / "default" / "memo" / "_index.json").write_text('{"id": "_index", "x": 1}')
        s.save({"id": "real"})
        records = s.load_all()
        assert [r["id"] for r in records] == ["real"]

    def test_skips_invalid_json(self, isolated_home):
        s = TenantStore("memo")
        (isolated_home / "tenants" / "default" / "memo").mkdir(parents=True, exist_ok=True)
        (isolated_home / "tenants" / "default" / "memo" / "bad.json").write_text("not valid json {")
        s.save({"id": "good"})
        records = s.load_all()
        # 解析失败的 bad.json 被跳过, 只留 good
        assert [r["id"] for r in records] == ["good"]

    def test_skips_missing_id_field(self, isolated_home):
        s = TenantStore("memo")
        (isolated_home / "tenants" / "default" / "memo").mkdir(parents=True, exist_ok=True)
        (isolated_home / "tenants" / "default" / "memo" / "no_id.json").write_text('{"text": "hi"}')
        s.save({"id": "good"})
        records = s.load_all()
        assert [r["id"] for r in records] == ["good"]

    def test_skips_non_dict_json(self, isolated_home):
        s = TenantStore("memo")
        (isolated_home / "tenants" / "default" / "memo").mkdir(parents=True, exist_ok=True)
        (isolated_home / "tenants" / "default" / "memo" / "list.json").write_text("[1, 2, 3]")
        s.save({"id": "good"})
        records = s.load_all()
        assert [r["id"] for r in records] == ["good"]

    def test_skips_non_dict_skills_field(self, isolated_home):
        """如果 skills 字段是 list 而非 dict, 应安全降级返 []。"""
        s = TenantStore("memo")
        (isolated_home / "tenants" / "default" / "memo").mkdir(parents=True, exist_ok=True)
        (isolated_home / "tenants" / "default" / "memo" / "x.json").write_text('"plain string"')
        records = s.load_all()
        assert records == []


# ── load_one ──


class TestLoadOne:
    def test_returns_record_when_exists(self, isolated_home):
        s = TenantStore("memo")
        s.save({"id": "r1", "v": 1})
        rec = s.load_one("r1")
        assert rec == {"id": "r1", "v": 1}

    def test_returns_none_when_missing(self, isolated_home):
        s = TenantStore("memo")
        assert s.load_one("nope") is None

    def test_returns_none_when_id_mismatch(self, isolated_home):
        """文件存在但 id 字段与查询值不匹配 → None (防 collision)。"""
        s = TenantStore("memo")
        (isolated_home / "tenants" / "default" / "memo").mkdir(parents=True, exist_ok=True)
        (isolated_home / "tenants" / "default" / "memo" / "r1.json").write_text('{"id": "different"}')
        assert s.load_one("r1") is None

    def test_returns_none_on_invalid_json(self, isolated_home):
        s = TenantStore("memo")
        (isolated_home / "tenants" / "default" / "memo").mkdir(parents=True, exist_ok=True)
        (isolated_home / "tenants" / "default" / "memo" / "r1.json").write_text("{not valid")
        assert s.load_one("r1") is None

    def test_returns_none_when_storage_dir_missing(self, isolated_home):
        s = TenantStore("never_created")
        assert s.load_one("anything") is None


# ── delete ──


class TestDelete:
    def test_returns_true_when_file_deleted(self, isolated_home):
        s = TenantStore("memo")
        s.save({"id": "x"})
        assert s.delete("x") is True
        assert not (isolated_home / "tenants" / "default" / "memo" / "x.json").exists()

    def test_returns_false_when_missing(self, isolated_home):
        s = TenantStore("memo")
        assert s.delete("nope") is False

    def test_returns_false_when_dir_missing(self, isolated_home):
        s = TenantStore("never_created")
        assert s.delete("anything") is False


# ── count ──


class TestCount:
    def test_count_zero_when_empty(self, isolated_home):
        s = TenantStore("memo")
        assert s.count() == 0

    def test_count_all_records(self, isolated_home):
        s = TenantStore("memo")
        s.save({"id": "a"})
        s.save({"id": "b"})
        s.save({"id": "c"})
        assert s.count() == 3

    def test_count_with_predicate_filters(self, isolated_home):
        s = TenantStore("memo")
        s.save({"id": "a", "active": True})
        s.save({"id": "b", "active": False})
        s.save({"id": "c", "active": True})
        assert s.count() == 3
        assert s.count(predicate=lambda r: r.get("active")) == 2
        assert s.count(predicate=lambda r: r["id"] == "a") == 1

    def test_count_with_always_false_predicate(self, isolated_home):
        s = TenantStore("memo")
        s.save({"id": "a"})
        assert s.count(predicate=lambda r: False) == 0


# ── 静态契约 ──


class TestStaticContract:
    def test_tenant_store_class_exported(self):
        from butler.tools import tenant_store
        assert hasattr(tenant_store, "TenantStore")
        assert hasattr(tenant_store, "logger")

    def test_init_signature(self):
        """__init__ 接受 subdir + env_toggle + skip_files。"""
        import inspect
        sig = inspect.signature(TenantStore.__init__)
        params = list(sig.parameters.keys())
        assert "subdir" in params
        assert "env_toggle" in params
        assert "skip_files" in params

    def test_skip_files_default_empty_frozenset(self):
        s = TenantStore("memo")
        assert s._skip_files == frozenset()
