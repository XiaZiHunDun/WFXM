"""Tests for Lead user-specified delegate role override."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.tools.delegate_phases import DelegateRunState
from butler.tools.delegate_role_guard import (
    apply_user_role_override,
    user_explicit_delegate_role,
)


class TestUserExplicitDelegateRole:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("请 delegate_task，role=dev（禁止用 content）", "dev"),
            ("委派开发写 docs/foo.md", "dev"),
            ("交给开发代理检查", "dev"),
            ("role=content 写文案", "content"),
            ("内容代理写一章", "content"),
            ("禁止 dev，用 content", "content"),
            ("随便写个文件", None),
        ],
    )
    def test_detect_explicit_role(self, text: str, expected: str | None):
        assert user_explicit_delegate_role(text) == expected

    def test_role_param_beats_mixed_signals(self):
        text = "role=dev 但不要 content 也不要 dev 乱写"
        assert user_explicit_delegate_role(text) == "dev"

    def test_skill_injection_does_not_steal_role(self):
        text = (
            "请 delegate_task，role=dev（禁止用 content）：写 docs/foo.md\n\n"
            "## 相关知识（Butler Skill）\n"
            "Use role=review for QA."
        )
        assert user_explicit_delegate_role(text) == "dev"


class TestApplyUserRoleOverride:
    def test_overrides_content_to_dev_on_lead_turn(self):
        state = DelegateRunState(role="content", task="写 docs/x.md", depth=0)
        orch = MagicMock()
        proj = MagicMock()
        proj.name = "灵文1号"
        orch.project_manager.get_current.return_value = proj
        with (
            patch(
                "butler.tools.delegate_role_guard._is_lead_turn",
                return_value=True,
            ),
            patch(
                "butler.tools.delegate_role_guard._turn_user_text",
                return_value="role=dev 禁止 content",
            ),
        ):
            assert apply_user_role_override(state) is True
        assert state.role == "dev"
        assert "[role_override]" in state.context

    def test_skips_when_not_lead(self):
        state = DelegateRunState(role="content", task="写 docs", depth=0)
        with patch(
            "butler.tools.delegate_role_guard._is_lead_turn",
            return_value=False,
        ):
            assert apply_user_role_override(state) is False
        assert state.role == "content"

    def test_explicit_role_from_task_blob(self):
        from butler.tools.delegate_phases import DelegateRunState
        from butler.tools.delegate_role_guard import _explicit_role_from_state

        state = DelegateRunState(
            role="review",
            task="write docs/foo.md",
            context="用户原话：role=dev 禁止 content",
        )
        assert _explicit_role_from_state(state) == "dev"

    def test_skips_nested_delegate(self):
        state = DelegateRunState(role="content", task="x", depth=1)
        with patch(
            "butler.tools.delegate_role_guard._is_lead_turn",
            return_value=True,
        ):
            assert apply_user_role_override(state) is False
