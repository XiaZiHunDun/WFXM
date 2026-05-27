"""Tests for butler.tools.expense — personal expense tracker."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("BUTLER_MODEL", "test-dummy")

from butler.tools.expense import (
    _normalize_category,
    _normalize_direction,
    format_expense_for_wechat,
    register_expense_tools,
    tool_expense_add,
    tool_expense_delete,
    tool_expense_list,
    tool_expense_summary,
)


@pytest.fixture(autouse=True)
def _tmp_expenses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    expenses_dir = tmp_path / "expenses"
    expenses_dir.mkdir()
    monkeypatch.setattr("butler.tools.expense._expenses_dir", lambda: expenses_dir)
    monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "1")
    yield expenses_dir


class TestNormalization:
    def test_category_valid(self):
        assert _normalize_category("food") == "food"
        assert _normalize_category("TRANSPORT") == "transport"

    def test_category_invalid(self):
        assert _normalize_category("bogus") == "other"
        assert _normalize_category("") == "other"

    def test_direction_valid(self):
        assert _normalize_direction("income") == "income"
        assert _normalize_direction("EXPENSE") == "expense"

    def test_direction_invalid(self):
        assert _normalize_direction("") == "expense"
        assert _normalize_direction("xyz") == "expense"


class TestExpenseAdd:
    def test_basic_add(self):
        data = json.loads(tool_expense_add(amount=35, description="午饭"))
        assert data["ok"] is True
        assert data["amount"] == 35.0
        assert data["direction"] == "expense"
        assert data["category"] == "other"

    def test_add_with_category(self):
        data = json.loads(tool_expense_add(amount=100, category="food", description="晚餐"))
        assert data["category"] == "food"

    def test_add_income(self):
        data = json.loads(tool_expense_add(amount=15000, direction="income", description="工资"))
        assert data["direction"] == "income"

    def test_add_with_date(self):
        data = json.loads(tool_expense_add(amount=50, date="2026-05-20"))
        assert data["date"] == "2026-05-20"

    def test_add_invalid_amount(self):
        data = json.loads(tool_expense_add(amount="abc"))
        assert data["ok"] is False

    def test_add_zero_amount(self):
        data = json.loads(tool_expense_add(amount=0))
        assert data["ok"] is False

    def test_add_negative_amount(self):
        data = json.loads(tool_expense_add(amount=-10))
        assert data["ok"] is False

    def test_add_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "0")
        data = json.loads(tool_expense_add(amount=10))
        assert data["ok"] is False


class TestExpenseSummary:
    def test_summary_empty(self):
        data = json.loads(tool_expense_summary())
        assert data["ok"] is True
        assert data["record_count"] == 0

    def test_summary_with_data(self):
        from butler.tools.expense import _today_str
        today = _today_str()
        tool_expense_add(amount=35, category="food", date=today)
        tool_expense_add(amount=20, category="transport", date=today)
        tool_expense_add(amount=5000, direction="income", category="salary", date=today)

        data = json.loads(tool_expense_summary(period="month"))
        assert data["record_count"] == 3
        assert data["total_expense"] == 55.0
        assert data["total_income"] == 5000.0
        assert data["net"] == 4945.0
        assert len(data["category_breakdown"]) == 2

    def test_summary_week(self):
        from butler.tools.expense import _today_str
        tool_expense_add(amount=100, date=_today_str())
        data = json.loads(tool_expense_summary(period="week"))
        assert data["ok"] is True
        assert data["record_count"] >= 1

    def test_summary_year(self):
        from butler.tools.expense import _today_str
        tool_expense_add(amount=100, date=_today_str())
        data = json.loads(tool_expense_summary(period="year"))
        assert data["ok"] is True


class TestExpenseList:
    def test_list_empty(self):
        data = json.loads(tool_expense_list())
        assert data["total"] == 0

    def test_list_records(self):
        tool_expense_add(amount=35, category="food")
        tool_expense_add(amount=20, category="transport")
        data = json.loads(tool_expense_list())
        assert data["total"] == 2

    def test_list_filter_category(self):
        tool_expense_add(amount=35, category="food")
        tool_expense_add(amount=20, category="transport")
        data = json.loads(tool_expense_list(category="food"))
        assert data["count"] == 1

    def test_list_filter_direction(self):
        tool_expense_add(amount=35)
        tool_expense_add(amount=5000, direction="income")
        data = json.loads(tool_expense_list(direction="income"))
        assert data["count"] == 1


class TestExpenseDelete:
    def test_delete_existing(self):
        rid = json.loads(tool_expense_add(amount=10))["record_id"]
        data = json.loads(tool_expense_delete(record_id=rid))
        assert data["ok"] is True
        assert json.loads(tool_expense_list())["total"] == 0

    def test_delete_prefix(self):
        rid = json.loads(tool_expense_add(amount=10))["record_id"]
        data = json.loads(tool_expense_delete(record_id=rid[:4]))
        assert data["ok"] is True

    def test_delete_not_found(self):
        data = json.loads(tool_expense_delete(record_id="nope"))
        assert data["ok"] is False

    def test_delete_empty_id(self):
        data = json.loads(tool_expense_delete(record_id=""))
        assert data["ok"] is False


class TestWeChat:
    def test_wechat_empty(self):
        result = format_expense_for_wechat()
        assert "暂无记录" in result

    def test_wechat_summary(self):
        from butler.tools.expense import _today_str
        tool_expense_add(amount=35, category="food", date=_today_str())
        result = format_expense_for_wechat("本月")
        assert "支出" in result
        assert "35" in result

    def test_wechat_quick_add(self):
        result = format_expense_for_wechat("记 午饭 35")
        assert "已记录" in result
        assert "35" in result

    def test_wechat_quick_add_amount_first(self):
        result = format_expense_for_wechat("记 35 午饭")
        assert "已记录" in result

    def test_wechat_quick_add_no_amount(self):
        result = format_expense_for_wechat("记 午饭")
        assert "金额" in result

    def test_wechat_recent(self):
        tool_expense_add(amount=100)
        result = format_expense_for_wechat("明细")
        assert "100" in result

    def test_wechat_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "0")
        assert "未启用" in format_expense_for_wechat()


class TestExpenseAddEdgeCases:
    def test_add_float_precision(self):
        data = json.loads(tool_expense_add(amount=10.555))
        assert data["amount"] == 10.56 or data["amount"] == 10.55

    def test_add_string_amount(self):
        data = json.loads(tool_expense_add(amount="35.5"))
        assert data["ok"] is True
        assert data["amount"] == 35.5

    def test_add_with_tags(self):
        data = json.loads(tool_expense_add(amount=100, tags=["公司报销"]))
        assert data["ok"] is True

    def test_add_with_tags_string(self):
        data = json.loads(tool_expense_add(amount=100, tags="日常,必要"))
        assert data["ok"] is True

    def test_add_bad_date_uses_today(self):
        from butler.tools.expense import _today_str
        data = json.loads(tool_expense_add(amount=10, date="bad-date"))
        assert data["date"] == _today_str()

    def test_add_description_truncated(self):
        long_desc = "x" * 300
        tool_expense_add(amount=10, description=long_desc)
        data = json.loads(tool_expense_list(limit=1))
        assert len(data["records"][0]["description"]) == 200

    def test_add_none_amount(self):
        data = json.loads(tool_expense_add(amount=None))
        assert data["ok"] is False


class TestExpenseSummaryEdgeCases:
    def test_summary_category_sorted_by_amount(self):
        from butler.tools.expense import _today_str
        today = _today_str()
        tool_expense_add(amount=10, category="food", date=today)
        tool_expense_add(amount=50, category="transport", date=today)
        tool_expense_add(amount=30, category="shopping", date=today)
        data = json.loads(tool_expense_summary(period="month"))
        cats = [c["category"] for c in data["category_breakdown"]]
        assert cats[0] == "transport"

    def test_summary_income_not_in_breakdown(self):
        from butler.tools.expense import _today_str
        today = _today_str()
        tool_expense_add(amount=5000, direction="income", category="salary", date=today)
        tool_expense_add(amount=100, category="food", date=today)
        data = json.loads(tool_expense_summary())
        cats = [c["category"] for c in data["category_breakdown"]]
        assert "salary" not in cats

    def test_summary_specific_month(self):
        tool_expense_add(amount=100, date="2026-03-15")
        data = json.loads(tool_expense_summary(year=2026, month=3))
        assert data["record_count"] == 1
        assert data["total_expense"] == 100.0

    def test_summary_cross_month_isolation(self):
        tool_expense_add(amount=100, date="2026-04-15")
        tool_expense_add(amount=200, date="2026-05-15")
        apr = json.loads(tool_expense_summary(year=2026, month=4))
        may = json.loads(tool_expense_summary(year=2026, month=5))
        assert apr["total_expense"] == 100.0
        assert may["total_expense"] == 200.0

    def test_summary_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "0")
        data = json.loads(tool_expense_summary())
        assert data["ok"] is False


class TestExpenseListEdgeCases:
    def test_list_sorted_by_date_desc(self):
        tool_expense_add(amount=10, date="2026-05-01", description="earlier")
        tool_expense_add(amount=20, date="2026-05-20", description="later")
        data = json.loads(tool_expense_list())
        assert data["records"][0]["description"] == "later"

    def test_list_limit_bounds(self):
        for i in range(5):
            tool_expense_add(amount=10 + i)
        data = json.loads(tool_expense_list(limit=100))
        assert len(data["records"]) == 5

    def test_list_combined_filters(self):
        tool_expense_add(amount=100, category="food", direction="expense")
        tool_expense_add(amount=200, category="food", direction="income")
        tool_expense_add(amount=300, category="transport")
        data = json.loads(tool_expense_list(category="food", direction="expense"))
        assert data["count"] == 1

    def test_list_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "0")
        data = json.loads(tool_expense_list())
        assert data["ok"] is False


class TestWeChatEdgeCases:
    def test_wechat_week_period(self):
        from butler.tools.expense import _today_str
        tool_expense_add(amount=50, date=_today_str())
        result = format_expense_for_wechat("本周")
        assert "支出" in result

    def test_wechat_year_period(self):
        from butler.tools.expense import _today_str
        tool_expense_add(amount=50, date=_today_str())
        result = format_expense_for_wechat("年度")
        assert "支出" in result or "暂无" in result

    def test_wechat_quick_add_with_yuan(self):
        result = format_expense_for_wechat("记 午饭 35元")
        assert "已记录" in result
        assert "35" in result

    def test_wechat_quick_add_with_kuai(self):
        result = format_expense_for_wechat("记 打车 20块")
        assert "已记录" in result

    def test_wechat_quick_add_no_arg(self):
        result = format_expense_for_wechat("记")
        assert "暂无记录" in result or "用法" in result or "汇总" in result

    def test_wechat_default_is_month_summary(self):
        result = format_expense_for_wechat("")
        assert "暂无记录" in result or "汇总" in result

    def test_wechat_summary_with_income(self):
        from butler.tools.expense import _today_str
        today = _today_str()
        tool_expense_add(amount=5000, direction="income", date=today)
        tool_expense_add(amount=100, date=today)
        result = format_expense_for_wechat("本月")
        assert "收入" in result
        assert "结余" in result

    def test_wechat_category_bar_chart(self):
        from butler.tools.expense import _today_str
        today = _today_str()
        tool_expense_add(amount=100, category="food", date=today)
        tool_expense_add(amount=50, category="transport", date=today)
        result = format_expense_for_wechat("本月")
        assert "分类明细" in result
        assert "█" in result


class TestRegistration:
    def test_register(self):
        registered = {}
        register_expense_tools(lambda name, **kw: registered.update({name: kw}))
        expected = {"expense_add", "expense_summary", "expense_list", "expense_delete"}
        assert set(registered.keys()) == expected
        for info in registered.values():
            assert info.get("toolset") == "expense"

    def test_register_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "0")
        registered = {}
        register_expense_tools(lambda name, **kw: registered.update({name: kw}))
        assert len(registered) == 0
