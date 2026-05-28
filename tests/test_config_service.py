"""Tests for butler.config_service — runtime config read/write."""

from __future__ import annotations

import os
import pytest


class TestConfigGet:
    def test_known_key_default(self):
        from butler.config_service import config_get

        cv = config_get("BUTLER_ENABLE_WEB_FETCH")
        assert cv.key == "BUTLER_ENABLE_WEB_FETCH"
        assert cv.meta is not None
        assert cv.meta.category == "网络"

    def test_unknown_key(self):
        from butler.config_service import config_get

        cv = config_get("BUTLER_NONEXISTENT_KEY_XYZ")
        assert cv.source == "unknown"

    def test_env_override(self, monkeypatch):
        from butler.config_service import config_get

        monkeypatch.setenv("BUTLER_ENABLE_WEB_FETCH", "1")
        cv = config_get("BUTLER_ENABLE_WEB_FETCH")
        assert cv.effective == "1"
        assert cv.source == "env"


class TestConfigSet:
    def test_set_valid_bool(self, monkeypatch):
        from butler.config_service import config_set

        monkeypatch.delenv("BUTLER_ENABLE_WEB_FETCH", raising=False)
        result = config_set("BUTLER_ENABLE_WEB_FETCH", "1")
        assert result.ok
        assert os.environ["BUTLER_ENABLE_WEB_FETCH"] == "1"

    def test_set_invalid_bool(self):
        from butler.config_service import config_set

        result = config_set("BUTLER_ENABLE_WEB_FETCH", "maybe")
        assert not result.ok

    def test_set_disallowed_key(self):
        from butler.config_service import config_set

        result = config_set("BUTLER_HOME", "/tmp")
        assert not result.ok
        assert "白名单" in result.message

    def test_case_insensitive(self, monkeypatch):
        from butler.config_service import config_set

        monkeypatch.delenv("BUTLER_ENABLE_WEB_FETCH", raising=False)
        result = config_set("butler_enable_web_fetch", "1")
        assert result.ok


class TestConfigList:
    def test_list_all(self):
        from butler.config_service import config_list

        items = config_list()
        assert len(items) > 10

    def test_list_by_category(self):
        from butler.config_service import config_list

        items = config_list("网络")
        assert all(cv.meta and cv.meta.category == "网络" for cv in items)
        assert len(items) >= 3

    def test_list_invalid_category(self):
        from butler.config_service import config_list

        items = config_list("不存在的分组")
        assert len(items) == 0


class TestFormatting:
    def test_format_list(self):
        from butler.config_service import format_config_list

        text = format_config_list()
        assert "配置分组" in text

    def test_format_get(self):
        from butler.config_service import format_config_get

        text = format_config_get("BUTLER_ENABLE_WEB_FETCH")
        assert "BUTLER_ENABLE_WEB_FETCH" in text
        assert "说明" in text


class TestConfigTool:
    def test_tool_list(self):
        import json
        from butler.tools.config_tools import tool_butler_config

        raw = tool_butler_config(action="list", category="网络")
        data = json.loads(raw)
        assert data["ok"]
        assert data["count"] >= 3

    def test_tool_get(self):
        import json
        from butler.tools.config_tools import tool_butler_config

        raw = tool_butler_config(action="get", key="BUTLER_ENABLE_WEB_FETCH")
        data = json.loads(raw)
        assert data["key"] == "BUTLER_ENABLE_WEB_FETCH"

    def test_tool_set(self, monkeypatch):
        import json
        from butler.tools.config_tools import tool_butler_config

        monkeypatch.delenv("BUTLER_MEMO_ENABLED", raising=False)
        raw = tool_butler_config(action="set", key="BUTLER_MEMO_ENABLED", value="0")
        data = json.loads(raw)
        assert data["ok"]
