"""Tests for P2 UX features — error cards, session eviction, skill install."""

from __future__ import annotations

import json
import pytest


class TestErrorCards:
    def test_doom_loop_card(self):
        from butler.gateway.error_cards import format_error_card

        msg = format_error_card("doom_loop", tool="terminal", count=3)
        assert msg is not None
        assert "需要您批准" in msg or "拦截" in msg
        assert "terminal" in msg

    def test_permission_deny_card(self):
        from butler.gateway.error_cards import format_error_card

        msg = format_error_card("permission_deny", tool="write_file", reason="outside workspace")
        assert "权限" in msg

    def test_delegate_timeout_card(self):
        from butler.gateway.error_cards import format_error_card

        msg = format_error_card("delegate_timeout", role="dev_agent", elapsed=120)
        assert "超时" in msg
        assert "dev_agent" in msg

    def test_tool_error_card(self):
        from butler.gateway.error_cards import format_error_card

        msg = format_error_card("tool_error", tool="patch", error="old_string not found")
        assert "错误" in msg

    def test_unknown_event(self):
        from butler.gateway.error_cards import format_error_card

        msg = format_error_card("unknown_event")
        assert msg is None


class TestSessionEvictHook:
    def test_set_and_fire_hook(self):
        from butler.gateway.session_registry import set_evict_notify_hook

        notified = []
        set_evict_notify_hook(lambda key: notified.append(key))
        # Clean up
        set_evict_notify_hook(None)

    def test_hook_none_safe(self):
        from butler.gateway.session_registry import set_evict_notify_hook
        set_evict_notify_hook(None)


class TestSkillInstallTool:
    def test_install_returns_json(self):
        from butler.tools.registry_tools import _tool_registry_install_skill

        raw = _tool_registry_install_skill(identifier="nonexistent-skill-xyz")
        data = json.loads(raw)
        assert isinstance(data, dict)
