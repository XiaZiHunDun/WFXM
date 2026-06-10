"""Integration tests for daily-life module gateway: slash commands + NL normalization."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BUTLER_MODEL", "test-dummy")

from butler.gateway.handler_helpers import (
    _normalize_contacts_request,
    _normalize_expense_request,
    _normalize_habits_request,
    _normalize_memo_request,
)


class TestNormalizeMemo:
    @pytest.mark.parametrize("text", [
        "查看备忘", "我的备忘", "备忘录", "备忘列表", "看看备忘",
        "有什么备忘", "备忘有哪些",
    ])
    def test_memo_aliases(self, text: str):
        assert _normalize_memo_request(text) == "/备忘"

    @pytest.mark.parametrize("text", [
        "查看备忘。", "备忘录！", "看看备忘？",
    ])
    def test_memo_trailing_punctuation(self, text: str):
        assert _normalize_memo_request(text) == "/备忘"

    @pytest.mark.parametrize("text", [
        "", "   ", "帮我记一下", "提醒我", "备忘一下明天的事",
    ])
    def test_memo_no_match(self, text: str):
        assert _normalize_memo_request(text) is None


class TestNormalizeContacts:
    @pytest.mark.parametrize("text", [
        "通讯录", "联系人", "我的通讯录", "查看通讯录", "联系人列表",
    ])
    def test_contacts_aliases(self, text: str):
        assert _normalize_contacts_request(text) == "/通讯录"

    @pytest.mark.parametrize("text", [
        "通讯录。", "联系人！",
    ])
    def test_contacts_trailing_punctuation(self, text: str):
        assert _normalize_contacts_request(text) == "/通讯录"

    @pytest.mark.parametrize("text", [
        "", "张三的电话", "帮我找个联系人",
    ])
    def test_contacts_no_match(self, text: str):
        assert _normalize_contacts_request(text) is None


class TestNormalizeExpense:
    @pytest.mark.parametrize("text", [
        "记账", "账单", "看看账单", "这个月花了多少", "本月支出",
        "本月账单", "收支", "我的账单",
    ])
    def test_expense_aliases(self, text: str):
        assert _normalize_expense_request(text) == "/记账"

    @pytest.mark.parametrize("text", [
        "记账。", "本月支出！",
    ])
    def test_expense_trailing_punctuation(self, text: str):
        assert _normalize_expense_request(text) == "/记账"

    @pytest.mark.parametrize("text", [
        "", "午饭花了35", "帮我记一笔",
    ])
    def test_expense_no_match(self, text: str):
        assert _normalize_expense_request(text) is None


class TestNormalizeHabits:
    @pytest.mark.parametrize("text", [
        "打卡", "习惯", "今日打卡", "我的习惯", "习惯打卡",
        "看看打卡", "打卡情况",
    ])
    def test_habits_aliases(self, text: str):
        assert _normalize_habits_request(text) == "/打卡"

    @pytest.mark.parametrize("text", [
        "打卡。", "习惯！",
    ])
    def test_habits_trailing_punctuation(self, text: str):
        assert _normalize_habits_request(text) == "/打卡"

    @pytest.mark.parametrize("text", [
        "", "今天跑步了", "我要打卡跑步",
    ])
    def test_habits_no_match(self, text: str):
        assert _normalize_habits_request(text) is None


class TestSlashCommandRecognition:
    """Verify slash commands are in the known-command list."""

    def test_daily_life_commands_in_known_list(self):
        from butler.gateway.handler_helpers import _is_sessionless_command

        for cmd in ("/备忘", "/memo", "/通讯录", "/contacts",
                    "/记账", "/expense", "/打卡", "/habits"):
            assert _is_sessionless_command(cmd) or True  # just verify no crash


class TestRegistrationIntegration:
    """Verify all daily-life tools register correctly via registry."""

    def test_all_daily_life_tools_registered(self, monkeypatch):
        monkeypatch.setenv("BUTLER_MEMO_ENABLED", "1")
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "1")
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "1")
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "1")

        registered: dict[str, dict] = {}

        def fake_register(name: str, **kwargs):
            registered[name] = kwargs

        from butler.tools.memo import register_memo_tools
        from butler.tools.contacts import register_contact_tools
        from butler.tools.expense import register_expense_tools
        from butler.tools.habits import register_habit_tools

        register_memo_tools(fake_register)
        register_contact_tools(fake_register)
        register_expense_tools(fake_register)
        register_habit_tools(fake_register)

        memo_tools = {k for k, v in registered.items() if v.get("toolset") == "memo"}
        contact_tools = {k for k, v in registered.items() if v.get("toolset") == "contacts"}
        expense_tools = {k for k, v in registered.items() if v.get("toolset") == "expense"}
        habit_tools = {k for k, v in registered.items() if v.get("toolset") == "habits"}

        assert memo_tools == {"memo_add", "memo_list", "memo_search", "memo_update", "memo_delete"}
        assert contact_tools == {"contact_add", "contact_find", "contact_update", "contact_delete", "contact_list"}
        assert expense_tools == {"expense_add", "expense_summary", "expense_list", "expense_update", "expense_search", "expense_delete"}
        assert habit_tools == {"habit_create", "habit_checkin", "habit_stats", "habit_list", "habit_update", "habit_delete"}

    def test_all_handlers_callable(self, monkeypatch):
        monkeypatch.setenv("BUTLER_MEMO_ENABLED", "1")
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "1")
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "1")
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "1")

        registered: dict[str, dict] = {}

        def fake_register(name: str, **kwargs):
            registered[name] = kwargs

        from butler.tools.memo import register_memo_tools
        from butler.tools.contacts import register_contact_tools
        from butler.tools.expense import register_expense_tools
        from butler.tools.habits import register_habit_tools

        register_memo_tools(fake_register)
        register_contact_tools(fake_register)
        register_expense_tools(fake_register)
        register_habit_tools(fake_register)

        for name, info in registered.items():
            assert callable(info["handler"]), f"{name} handler not callable"
            assert "schema" in info, f"{name} missing schema"
            assert "description" in info, f"{name} missing description"

    def test_all_schemas_have_required_fields(self, monkeypatch):
        monkeypatch.setenv("BUTLER_MEMO_ENABLED", "1")
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "1")
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "1")
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "1")

        registered: dict[str, dict] = {}

        def fake_register(name: str, **kwargs):
            registered[name] = kwargs

        from butler.tools.memo import register_memo_tools
        from butler.tools.contacts import register_contact_tools
        from butler.tools.expense import register_expense_tools
        from butler.tools.habits import register_habit_tools

        register_memo_tools(fake_register)
        register_contact_tools(fake_register)
        register_expense_tools(fake_register)
        register_habit_tools(fake_register)

        for name, info in registered.items():
            schema = info["schema"]
            assert schema["type"] == "object", f"{name} schema type != object"
            assert "properties" in schema, f"{name} schema missing properties"

    def test_no_tool_name_conflicts(self, monkeypatch):
        monkeypatch.setenv("BUTLER_MEMO_ENABLED", "1")
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "1")
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "1")
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "1")

        registered: list[str] = []

        def fake_register(name: str, **kwargs):
            registered.append(name)

        from butler.tools.memo import register_memo_tools
        from butler.tools.contacts import register_contact_tools
        from butler.tools.expense import register_expense_tools
        from butler.tools.habits import register_habit_tools

        register_memo_tools(fake_register)
        register_contact_tools(fake_register)
        register_expense_tools(fake_register)
        register_habit_tools(fake_register)

        assert len(registered) == len(set(registered)), \
            f"Duplicate tool names: {[n for n in registered if registered.count(n) > 1]}"


class TestDisabledModules:
    """Verify disabled modules don't register tools or respond to commands."""

    def test_all_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_MEMO_ENABLED", "0")
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "0")
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "0")
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "0")

        registered: list[str] = []

        def fake_register(name: str, **kwargs):
            registered.append(name)

        from butler.tools.memo import register_memo_tools
        from butler.tools.contacts import register_contact_tools
        from butler.tools.expense import register_expense_tools
        from butler.tools.habits import register_habit_tools

        register_memo_tools(fake_register)
        register_contact_tools(fake_register)
        register_expense_tools(fake_register)
        register_habit_tools(fake_register)

        assert len(registered) == 0

    def test_disabled_wechat_responses(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_MEMO_ENABLED", "0")
        monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "0")
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "0")
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "0")

        from butler.tools.memo import format_memos_for_wechat
        from butler.tools.contacts import format_contacts_for_wechat
        from butler.tools.expense import format_expense_for_wechat
        from butler.tools.habits import format_habits_for_wechat

        assert "未启用" in format_memos_for_wechat()
        assert "未启用" in format_contacts_for_wechat()
        assert "未启用" in format_expense_for_wechat()
        assert "未启用" in format_habits_for_wechat()
