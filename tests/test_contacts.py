"""Tests for butler.tools.contacts — personal contacts manager."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("BUTLER_MODEL", "test-dummy")

from butler.tools.contacts import (
    _normalize_category,
    _normalize_emails,
    _normalize_phones,
    _normalize_tags,
    format_contacts_for_wechat,
    register_contact_tools,
    tool_contact_add,
    tool_contact_delete,
    tool_contact_find,
    tool_contact_list,
    tool_contact_update,
)


@pytest.fixture(autouse=True)
def _tmp_contacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    contacts_dir = tmp_path / "contacts"
    contacts_dir.mkdir()
    monkeypatch.setattr("butler.tools.contacts._contacts_dir", lambda: contacts_dir)
    monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "1")
    yield contacts_dir


class TestNormalization:
    def test_phones_string(self):
        assert _normalize_phones("138,139，140") == ["138", "139", "140"]

    def test_phones_list(self):
        assert _normalize_phones(["138", "139"]) == ["138", "139"]

    def test_phones_dedup(self):
        assert _normalize_phones(["138", "138"]) == ["138"]

    def test_emails_string(self):
        assert _normalize_emails("a@b.com, c@d.com") == ["a@b.com", "c@d.com"]

    def test_category(self):
        assert _normalize_category("work") == "work"
        assert _normalize_category("bogus") == "personal"
        assert _normalize_category("") == "personal"

    def test_tags(self):
        assert _normalize_tags("tag1, tag2") == ["tag1", "tag2"]
        assert _normalize_tags(None) == []


class TestContactAdd:
    def test_basic_add(self):
        data = json.loads(tool_contact_add(name="张三"))
        assert data["ok"] is True
        assert len(data["contact_id"]) == 10
        assert data["name"] == "张三"

    def test_add_with_details(self):
        data = json.loads(tool_contact_add(
            name="李医生",
            phone=["13800138000"],
            email=["li@hospital.com"],
            address="北京市朝阳区XX医院",
            category="medical",
            tags=["牙科"],
            notes="周一到周五上午出诊",
        ))
        assert data["ok"] is True

    def test_add_empty_name(self):
        data = json.loads(tool_contact_add(name=""))
        assert data["ok"] is False

    def test_add_duplicate_warning(self):
        tool_contact_add(name="张三")
        data = json.loads(tool_contact_add(name="张三"))
        assert data["ok"] is True
        assert "warning" in data

    def test_add_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "0")
        data = json.loads(tool_contact_add(name="x"))
        assert data["ok"] is False


class TestContactFind:
    def test_find_by_name(self):
        tool_contact_add(name="张三", phone=["138"])
        tool_contact_add(name="李四", phone=["139"])
        data = json.loads(tool_contact_find(query="张三"))
        assert data["count"] == 1
        assert data["contacts"][0]["name"] == "张三"

    def test_find_by_phone(self):
        tool_contact_add(name="张三", phone=["13800138000"])
        data = json.loads(tool_contact_find(query="13800"))
        assert data["count"] == 1

    def test_find_by_tag(self):
        tool_contact_add(name="王五", tags=["大学同学"])
        data = json.loads(tool_contact_find(query="大学同学"))
        assert data["count"] == 1

    def test_find_no_match(self):
        tool_contact_add(name="张三")
        data = json.loads(tool_contact_find(query="不存在"))
        assert data["count"] == 0

    def test_find_filter_category(self):
        tool_contact_add(name="张医生", category="medical")
        tool_contact_add(name="张朋友", category="personal")
        data = json.loads(tool_contact_find(query="张", category="medical"))
        assert data["count"] == 1


class TestContactUpdate:
    def test_update_phone(self):
        cid = json.loads(tool_contact_add(name="张三"))["contact_id"]
        data = json.loads(tool_contact_update(contact_id=cid, phone=["13900139000"]))
        assert data["ok"] is True
        assert data["updated"] is True

    def test_update_prefix(self):
        cid = json.loads(tool_contact_add(name="张三"))["contact_id"]
        data = json.loads(tool_contact_update(contact_id=cid[:4], notes="新备注"))
        assert data["ok"] is True

    def test_update_not_found(self):
        data = json.loads(tool_contact_update(contact_id="nope"))
        assert data["ok"] is False

    def test_update_empty_id(self):
        data = json.loads(tool_contact_update(contact_id=""))
        assert data["ok"] is False


class TestContactDelete:
    def test_delete_existing(self):
        cid = json.loads(tool_contact_add(name="张三"))["contact_id"]
        data = json.loads(tool_contact_delete(contact_id=cid))
        assert data["ok"] is True
        assert json.loads(tool_contact_list())["total"] == 0

    def test_delete_prefix(self):
        cid = json.loads(tool_contact_add(name="张三"))["contact_id"]
        data = json.loads(tool_contact_delete(contact_id=cid[:4]))
        assert data["ok"] is True

    def test_delete_not_found(self):
        data = json.loads(tool_contact_delete(contact_id="nope"))
        assert data["ok"] is False


class TestContactList:
    def test_list_empty(self):
        data = json.loads(tool_contact_list())
        assert data["total"] == 0

    def test_list_all(self):
        tool_contact_add(name="A")
        tool_contact_add(name="B")
        data = json.loads(tool_contact_list())
        assert data["total"] == 2

    def test_list_filter_category(self):
        tool_contact_add(name="A", category="work")
        tool_contact_add(name="B", category="personal")
        data = json.loads(tool_contact_list(category="work"))
        assert data["count"] == 1


class TestWeChat:
    def test_wechat_empty(self):
        result = format_contacts_for_wechat()
        assert "通讯录为空" in result

    def test_wechat_list(self):
        tool_contact_add(name="张三", phone=["138"])
        result = format_contacts_for_wechat()
        assert "张三" in result
        assert "1人" in result

    def test_wechat_add(self):
        result = format_contacts_for_wechat("添加 王五")
        assert "已添加" in result

    def test_wechat_find(self):
        tool_contact_add(name="张三", phone=["138"])
        result = format_contacts_for_wechat("找 张三")
        assert "张三" in result

    def test_wechat_delete(self):
        cid = json.loads(tool_contact_add(name="x"))["contact_id"]
        result = format_contacts_for_wechat(f"删除 {cid}")
        assert "已删除" in result

    def test_wechat_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "0")
        assert "未启用" in format_contacts_for_wechat()


class TestContactAddEdgeCases:
    def test_add_with_phone_string(self):
        data = json.loads(tool_contact_add(name="张三", phone="138,139"))
        assert data["ok"] is True
        found = json.loads(tool_contact_find(query="138"))
        assert found["count"] == 1

    def test_add_with_email_string(self):
        data = json.loads(tool_contact_add(name="张三", email="a@b.com;c@d.com"))
        assert data["ok"] is True

    def test_add_notes_truncated(self):
        long_notes = "x" * 600
        tool_contact_add(name="张三", notes=long_notes)
        data = json.loads(tool_contact_find(query="张三"))
        assert len(data["contacts"][0]["notes"]) == 500

    def test_add_whitespace_name(self):
        data = json.loads(tool_contact_add(name="   "))
        assert data["ok"] is False

    def test_add_limit(self):
        from unittest.mock import patch
        with patch("butler.tools.contacts._MAX_CONTACTS", 2):
            tool_contact_add(name="A")
            tool_contact_add(name="B")
            data = json.loads(tool_contact_add(name="C"))
            assert data["ok"] is False
            assert "limit" in data["error"].lower()


class TestContactFindEdgeCases:
    def test_find_by_email(self):
        tool_contact_add(name="张三", email=["test@example.com"])
        data = json.loads(tool_contact_find(query="test@example"))
        assert data["count"] == 1

    def test_find_by_address(self):
        tool_contact_add(name="张三", address="北京市朝阳区")
        data = json.loads(tool_contact_find(query="朝阳"))
        assert data["count"] == 1

    def test_find_by_notes(self):
        tool_contact_add(name="李医生", notes="每周三出诊")
        data = json.loads(tool_contact_find(query="出诊"))
        assert data["count"] == 1

    def test_find_empty_query_returns_all(self):
        tool_contact_add(name="A")
        tool_contact_add(name="B")
        data = json.loads(tool_contact_find(query=""))
        assert data["count"] == 2

    def test_find_sorted_by_name(self):
        tool_contact_add(name="Charlie")
        tool_contact_add(name="Alice")
        tool_contact_add(name="Bob")
        data = json.loads(tool_contact_find(query=""))
        names = [c["name"] for c in data["contacts"]]
        assert names == ["Alice", "Bob", "Charlie"]

    def test_find_limit(self):
        for i in range(5):
            tool_contact_add(name=f"user-{i}")
        data = json.loads(tool_contact_find(query="user", limit=2))
        assert len(data["contacts"]) == 2
        assert data["count"] == 5

    def test_find_case_insensitive(self):
        tool_contact_add(name="Zhang San")
        data = json.loads(tool_contact_find(query="zhang"))
        assert data["count"] == 1


class TestContactUpdateEdgeCases:
    def test_update_name(self):
        cid = json.loads(tool_contact_add(name="旧名"))["contact_id"]
        tool_contact_update(contact_id=cid, name="新名")
        data = json.loads(tool_contact_find(query="新名"))
        assert data["count"] == 1

    def test_update_category(self):
        cid = json.loads(tool_contact_add(name="张三"))["contact_id"]
        tool_contact_update(contact_id=cid, category="work")
        data = json.loads(tool_contact_find(query="张三"))
        assert data["contacts"][0]["category"] == "work"

    def test_update_no_change(self):
        cid = json.loads(tool_contact_add(name="张三"))["contact_id"]
        data = json.loads(tool_contact_update(contact_id=cid))
        assert data["updated"] is False

    def test_update_preserves_other_fields(self):
        cid = json.loads(tool_contact_add(
            name="张三", phone=["138"], email=["a@b.com"]
        ))["contact_id"]
        tool_contact_update(contact_id=cid, notes="new note")
        data = json.loads(tool_contact_find(query="张三"))
        c = data["contacts"][0]
        assert c["phone"] == ["138"]
        assert c["email"] == ["a@b.com"]


class TestContactListEdgeCases:
    def test_list_category_counts(self):
        tool_contact_add(name="A", category="work")
        tool_contact_add(name="B", category="work")
        tool_contact_add(name="C", category="personal")
        data = json.loads(tool_contact_list())
        assert data["categories"]["work"] == 2
        assert data["categories"]["personal"] == 1

    def test_list_limit(self):
        for i in range(5):
            tool_contact_add(name=f"user-{i}")
        data = json.loads(tool_contact_list(limit=2))
        assert len(data["contacts"]) == 2
        assert data["total"] == 5


class TestWeChatEdgeCases:
    def test_wechat_find_no_keyword_fallback(self):
        """No-space subcommand falls back to default list."""
        result = format_contacts_for_wechat("找")
        assert "通讯录" in result

    def test_wechat_find_no_match(self):
        result = format_contacts_for_wechat("找 不存在")
        assert "未找到" in result

    def test_wechat_add_no_name_fallback(self):
        result = format_contacts_for_wechat("添加")
        assert "通讯录" in result

    def test_wechat_delete_no_id_fallback(self):
        result = format_contacts_for_wechat("删除")
        assert "通讯录" in result

    def test_wechat_delete_invalid_id(self):
        result = format_contacts_for_wechat("删除 badid")
        assert "失败" in result or "not found" in result.lower()

    def test_wechat_detail_display(self):
        tool_contact_add(
            name="张三", phone=["138"], email=["a@b.com"],
            address="北京", notes="重要客户"
        )
        result = format_contacts_for_wechat("找 张三")
        assert "📞" in result
        assert "📧" in result
        assert "📍" in result
        assert "💬" in result

    def test_wechat_overflow_list(self):
        for i in range(25):
            tool_contact_add(name=f"user-{i:02d}")
        result = format_contacts_for_wechat()
        assert "还有" in result

    def test_wechat_category_icon(self):
        tool_contact_add(name="张医生", category="medical")
        result = format_contacts_for_wechat()
        assert "🏥" in result


class TestRegistration:
    def test_register(self):
        registered = {}
        register_contact_tools(lambda name, **kw: registered.update({name: kw}))
        expected = {"contact_add", "contact_find", "contact_update", "contact_delete", "contact_list"}
        assert set(registered.keys()) == expected
        for info in registered.values():
            assert info.get("toolset") == "contacts"

    def test_register_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "0")
        registered = {}
        register_contact_tools(lambda name, **kw: registered.update({name: kw}))
        assert len(registered) == 0
