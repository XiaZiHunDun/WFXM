"""Tests for butler.tools.memo — personal memo system."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("BUTLER_MODEL", "test-dummy")

from butler.tools.memo import (
    _normalize_category,
    _normalize_priority,
    _normalize_status,
    _normalize_tags,
    format_memos_for_wechat,
    register_memo_tools,
    tool_memo_add,
    tool_memo_delete,
    tool_memo_list,
    tool_memo_search,
    tool_memo_update,
)


@pytest.fixture(autouse=True)
def _tmp_memos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    memo_dir = tmp_path / "memos"
    memo_dir.mkdir()
    monkeypatch.setattr("butler.tools.memo._memos_dir", lambda: memo_dir)
    monkeypatch.setenv("BUTLER_MEMO_ENABLED", "1")
    yield memo_dir


class TestNormalization:
    def test_category_valid(self):
        assert _normalize_category("health") == "health"
        assert _normalize_category("FINANCE") == "finance"

    def test_category_invalid(self):
        assert _normalize_category("bogus") == "general"
        assert _normalize_category("") == "general"
        assert _normalize_category(None) == "general"

    def test_status_valid(self):
        assert _normalize_status("done") == "done"
        assert _normalize_status("ACTIVE") == "active"

    def test_status_invalid(self):
        assert _normalize_status("xyz") == "active"

    def test_priority_valid(self):
        assert _normalize_priority("urgent") == "urgent"
        assert _normalize_priority("LOW") == "low"

    def test_priority_invalid(self):
        assert _normalize_priority("") == "normal"

    def test_tags_from_string(self):
        assert _normalize_tags("a, b，c") == ["a", "b", "c"]

    def test_tags_from_list(self):
        assert _normalize_tags(["x", "y"]) == ["x", "y"]

    def test_tags_dedup(self):
        assert _normalize_tags(["a", "a", "b"]) == ["a", "b"]

    def test_tags_max(self):
        assert len(_normalize_tags([str(i) for i in range(20)])) == 10

    def test_tags_empty(self):
        assert _normalize_tags(None) == []
        assert _normalize_tags("") == []


class TestMemoAdd:
    def test_basic_add(self):
        raw = tool_memo_add(content="买牛奶")
        data = json.loads(raw)
        assert data["ok"] is True
        assert len(data["memo_id"]) == 10
        assert data["content"] == "买牛奶"
        assert data["category"] == "general"

    def test_add_with_fields(self):
        raw = tool_memo_add(
            content="体检",
            category="health",
            tags=["年度", "体检"],
            priority="high",
            due_date="2026-06-01",
        )
        data = json.loads(raw)
        assert data["ok"] is True
        assert data["due_date"] == "2026-06-01"
        assert "suggestion" in data

    def test_add_empty_content(self):
        data = json.loads(tool_memo_add(content=""))
        assert data["ok"] is False
        assert "content" in data["error"]

    def test_add_truncates_content(self):
        long = "x" * 3000
        data = json.loads(tool_memo_add(content=long))
        assert data["ok"] is True
        assert len(data["content"]) == 2000

    def test_add_limit(self, _tmp_memos: Path):
        with patch("butler.tools.memo._MAX_ACTIVE", 2):
            tool_memo_add(content="a")
            tool_memo_add(content="b")
            data = json.loads(tool_memo_add(content="c"))
            assert data["ok"] is False
            assert "limit" in data["error"].lower()

    def test_add_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_MEMO_ENABLED", "0")
        data = json.loads(tool_memo_add(content="x"))
        assert data["ok"] is False


class TestMemoList:
    def test_list_empty(self):
        data = json.loads(tool_memo_list())
        assert data["ok"] is True
        assert data["count"] == 0

    def test_list_active(self):
        tool_memo_add(content="a")
        tool_memo_add(content="b")
        data = json.loads(tool_memo_list())
        assert data["count"] == 2
        assert data["active_total"] == 2

    def test_list_filter_category(self):
        tool_memo_add(content="a", category="health")
        tool_memo_add(content="b", category="finance")
        data = json.loads(tool_memo_list(category="health"))
        assert data["count"] == 1
        assert data["memos"][0]["category"] == "health"

    def test_list_done(self):
        raw = tool_memo_add(content="task")
        mid = json.loads(raw)["memo_id"]
        tool_memo_update(memo_id=mid, status="done")
        data = json.loads(tool_memo_list(status="done"))
        assert data["count"] == 1

    def test_list_limit(self):
        for i in range(5):
            tool_memo_add(content=f"memo-{i}")
        data = json.loads(tool_memo_list(limit=2))
        assert len(data["memos"]) == 2
        assert data["count"] == 5


class TestMemoSearch:
    def test_search_by_content(self):
        tool_memo_add(content="买牛奶和面包")
        tool_memo_add(content="开会讨论项目")
        data = json.loads(tool_memo_search(query="牛奶"))
        assert data["count"] == 1
        assert "牛奶" in data["memos"][0]["content"]

    def test_search_by_tag(self):
        tool_memo_add(content="something", tags=["important"])
        data = json.loads(tool_memo_search(query="important"))
        assert data["count"] == 1

    def test_search_empty_query(self):
        tool_memo_add(content="a")
        data = json.loads(tool_memo_search(query=""))
        assert data["ok"] is True

    def test_search_no_match(self):
        tool_memo_add(content="hello")
        data = json.loads(tool_memo_search(query="xyz"))
        assert data["count"] == 0


class TestMemoUpdate:
    def test_update_status(self):
        mid = json.loads(tool_memo_add(content="task"))["memo_id"]
        data = json.loads(tool_memo_update(memo_id=mid, status="done"))
        assert data["ok"] is True
        assert data["updated"] is True
        assert data["status"] == "done"

    def test_update_content(self):
        mid = json.loads(tool_memo_add(content="old"))["memo_id"]
        tool_memo_update(memo_id=mid, content="new content")
        search = json.loads(tool_memo_search(query="new content"))
        assert search["count"] == 1

    def test_update_prefix_match(self):
        mid = json.loads(tool_memo_add(content="x"))["memo_id"]
        prefix = mid[:4]
        data = json.loads(tool_memo_update(memo_id=prefix, status="done"))
        assert data["ok"] is True

    def test_update_not_found(self):
        data = json.loads(tool_memo_update(memo_id="nonexistent"))
        assert data["ok"] is False

    def test_update_no_change(self):
        mid = json.loads(tool_memo_add(content="x"))["memo_id"]
        data = json.loads(tool_memo_update(memo_id=mid))
        assert data["ok"] is True
        assert data["updated"] is False

    def test_update_empty_id(self):
        data = json.loads(tool_memo_update(memo_id=""))
        assert data["ok"] is False


class TestMemoDelete:
    def test_delete_existing(self):
        mid = json.loads(tool_memo_add(content="bye"))["memo_id"]
        data = json.loads(tool_memo_delete(memo_id=mid))
        assert data["ok"] is True
        assert data["deleted"] == mid
        assert json.loads(tool_memo_list())["count"] == 0

    def test_delete_prefix(self):
        mid = json.loads(tool_memo_add(content="bye"))["memo_id"]
        data = json.loads(tool_memo_delete(memo_id=mid[:4]))
        assert data["ok"] is True

    def test_delete_not_found(self):
        data = json.loads(tool_memo_delete(memo_id="nope"))
        assert data["ok"] is False

    def test_delete_empty_id(self):
        data = json.loads(tool_memo_delete(memo_id=""))
        assert data["ok"] is False


class TestWeChat:
    def test_wechat_empty(self):
        result = format_memos_for_wechat()
        assert "备忘录为空" in result

    def test_wechat_list(self):
        tool_memo_add(content="买牛奶", priority="high")
        tool_memo_add(content="取快递")
        result = format_memos_for_wechat()
        assert "备忘录" in result
        assert "2条活跃" in result
        assert "买牛奶" in result

    def test_wechat_add(self):
        result = format_memos_for_wechat("添加 测试备忘")
        assert "备忘已添加" in result

    def test_wechat_done(self):
        raw = tool_memo_add(content="x")
        mid = json.loads(raw)["memo_id"]
        result = format_memos_for_wechat(f"完成 {mid}")
        assert "已标记完成" in result

    def test_wechat_search(self):
        tool_memo_add(content="重要会议")
        result = format_memos_for_wechat("搜索 会议")
        assert "1 条" in result

    def test_wechat_search_empty(self):
        result = format_memos_for_wechat("搜索 xyz")
        assert "未找到" in result

    def test_wechat_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_MEMO_ENABLED", "0")
        result = format_memos_for_wechat()
        assert "未启用" in result


class TestMemoSorting:
    def test_sort_by_priority(self):
        tool_memo_add(content="low", priority="low")
        tool_memo_add(content="urgent", priority="urgent")
        tool_memo_add(content="normal", priority="normal")
        data = json.loads(tool_memo_list())
        names = [m["content"] for m in data["memos"]]
        assert names[0] == "urgent"

    def test_sort_by_time_within_priority(self):
        import time
        tool_memo_add(content="first", priority="normal")
        time.sleep(0.01)
        tool_memo_add(content="second", priority="normal")
        data = json.loads(tool_memo_list())
        names = [m["content"] for m in data["memos"]]
        assert names.index("second") < names.index("first")


class TestMemoUpdateMultipleFields:
    def test_update_priority_and_tags(self):
        mid = json.loads(tool_memo_add(content="task"))["memo_id"]
        data = json.loads(tool_memo_update(
            memo_id=mid, priority="urgent", tags=["重要", "紧急"]
        ))
        assert data["ok"] is True
        assert data["updated"] is True
        found = json.loads(tool_memo_search(query="task"))
        assert found["memos"][0]["priority"] == "urgent"
        assert "重要" in found["memos"][0]["tags"]

    def test_update_due_date(self):
        mid = json.loads(tool_memo_add(content="x", due_date="2026-06-01"))["memo_id"]
        tool_memo_update(memo_id=mid, due_date="2026-07-01")
        found = json.loads(tool_memo_list())
        assert found["memos"][0].get("due_date") == "2026-07-01"

    def test_lifecycle_active_done_archived(self):
        mid = json.loads(tool_memo_add(content="task"))["memo_id"]
        tool_memo_update(memo_id=mid, status="done")
        assert json.loads(tool_memo_list(status="done"))["count"] == 1
        tool_memo_update(memo_id=mid, status="archived")
        assert json.loads(tool_memo_list(status="archived"))["count"] == 1
        assert json.loads(tool_memo_list(status="active"))["count"] == 0

    def test_update_preserves_unmodified_fields(self):
        mid = json.loads(tool_memo_add(
            content="original", category="health", tags=["tag1"]
        ))["memo_id"]
        tool_memo_update(memo_id=mid, priority="high")
        found = json.loads(tool_memo_search(query="original"))
        m = found["memos"][0]
        assert m["category"] == "health"
        assert m["tags"] == ["tag1"]


class TestMemoSearchEdgeCases:
    def test_search_case_insensitive(self):
        tool_memo_add(content="Hello World")
        data = json.loads(tool_memo_search(query="hello"))
        assert data["count"] == 1

    def test_search_across_statuses(self):
        mid = json.loads(tool_memo_add(content="findme"))["memo_id"]
        tool_memo_update(memo_id=mid, status="done")
        data = json.loads(tool_memo_search(query="findme"))
        assert data["count"] == 1

    def test_search_with_limit(self):
        for i in range(5):
            tool_memo_add(content=f"item-{i}")
        data = json.loads(tool_memo_search(query="item", limit=2))
        assert len(data["memos"]) == 2
        assert data["count"] == 5


class TestMemoWeChatEdgeCases:
    def test_wechat_add_no_arg_fallback(self):
        """No-space subcommand falls back to default list."""
        result = format_memos_for_wechat("添加")
        assert "备忘" in result

    def test_wechat_add_usage_hint(self):
        result = format_memos_for_wechat("add ")
        assert "用法" in result or "备忘" in result

    def test_wechat_done_invalid_id(self):
        result = format_memos_for_wechat("完成 invalid_id_xyz")
        assert "失败" in result or "not found" in result.lower()

    def test_wechat_search_no_arg_fallback(self):
        result = format_memos_for_wechat("搜索")
        assert "备忘" in result

    def test_wechat_priority_icons(self):
        tool_memo_add(content="紧急事务", priority="urgent")
        result = format_memos_for_wechat()
        assert "🔴" in result

    def test_wechat_category_display(self):
        tool_memo_add(content="看医生", category="health")
        result = format_memos_for_wechat()
        assert "健康" in result

    def test_wechat_due_date_display(self):
        tool_memo_add(content="会议", due_date="2026-06-15")
        result = format_memos_for_wechat()
        assert "2026-06-15" in result

    def test_wechat_overflow_list(self):
        for i in range(20):
            tool_memo_add(content=f"item-{i}")
        result = format_memos_for_wechat()
        assert "还有" in result

    def test_wechat_done_count_footer(self):
        mid = json.loads(tool_memo_add(content="a"))["memo_id"]
        tool_memo_update(memo_id=mid, status="done")
        tool_memo_add(content="b")
        result = format_memos_for_wechat()
        assert "已完成" in result


class TestRegistration:
    def test_register(self):
        registered: dict[str, dict] = {}

        def fake_register(name: str, **kwargs):
            registered[name] = kwargs

        register_memo_tools(fake_register)
        expected = {"memo_add", "memo_list", "memo_search", "memo_update", "memo_delete"}
        assert set(registered.keys()) == expected
        for name, info in registered.items():
            assert info.get("toolset") == "memo"
            assert callable(info.get("handler"))

    def test_register_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_MEMO_ENABLED", "0")
        registered: dict = {}
        register_memo_tools(lambda name, **kw: registered.update({name: kw}))
        assert len(registered) == 0
