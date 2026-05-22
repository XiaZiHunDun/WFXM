"""WeChat project onboarding commands."""

from __future__ import annotations

import pytest

from butler.gateway.project_commands import handle_project_onboarding_command


@pytest.mark.unit
class TestProjectCommands:
    def test_preflight_requires_project(self):
        from unittest.mock import MagicMock

        orch = MagicMock()
        orch.project_manager.resolve_active_project_name.return_value = ""
        orch.project_manager.get_current.return_value = None
        out = handle_project_onboarding_command(
            orch, "/项目", "体检", session_key="wechat:u:default",
        )
        assert out is not None
        assert "切换" in out
