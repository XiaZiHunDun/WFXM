"""WeChat project onboarding commands."""

from __future__ import annotations

import pytest

from butler.gateway.commands.project_handlers import handle_project_onboarding_command


@pytest.mark.unit
class TestProjectCommands:
    def test_create_denied_without_owner(self, monkeypatch):
        from unittest.mock import MagicMock

        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "only-owner")
        orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        out = handle_project_onboarding_command(
            orch,
            "/项目",
            "新建 MyApp",
            session_key="wechat:u:default",
            platform="wechat",
            external_id="not-owner",
        )
        assert out is not None
        assert "Owner" in out or "主公" in out

    def test_preflight_requires_project(self):
        from unittest.mock import MagicMock

        orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch.project_manager.resolve_active_project_name.return_value = ""
        orch.project_manager.get_current.return_value = None
        out = handle_project_onboarding_command(
            orch, "/项目", "体检", session_key="wechat:u:default",
        )
        assert out is not None
        assert "切换" in out
