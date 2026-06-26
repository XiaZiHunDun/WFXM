"""PROD-P4 Owner UX unit tests."""

from __future__ import annotations

import pytest

from butler.gateway.owner_surface import (
    format_owner_diagnostic_brief,
    format_owner_help_default,
)
from butler.report.acceptance_card import (
    attach_delegate_acceptance_meta,
    format_delegate_acceptance_card,
)
from butler.report.generator import AgentReport, Change, format_for_wechat


@pytest.mark.unit
def test_help_five_intents_keywords():
    text = format_owner_help_default()
    assert "五个说法" in text
    for intent in ("查", "改", "批", "记", "管"):
        assert intent in text


@pytest.mark.unit
def test_diagnostic_brief_no_ot2():
    from unittest.mock import MagicMock
    from types import SimpleNamespace

    orch = MagicMock()
    orch._settings.default_provider = "minimax"
    orch.project_manager.get_current.return_value = SimpleNamespace(name="Demo")
    text = format_owner_diagnostic_brief(orch, "sk1")
    assert "OT2" not in text
    assert "G1-04" not in text


@pytest.mark.unit
def test_acceptance_card_verify_pass():
    report = AgentReport(
        headline="开发代理已完成任务",
        success=True,
        task_id="task_abc",
        changes=[Change(file="a.py", action="modified", description="")],
    )
    attach_delegate_acceptance_meta(
        report,
        role="dev",
        project=type("P", (), {"dev": {"test_command": "pytest -q"}})(),
        dev_engine={"verify_passed": True, "edits": 1},
    )
    card = format_delegate_acceptance_card(report)
    assert "验收卡" in card
    assert "测试：✅ 通过" in card
    assert "变更：" in card
    assert "/详细" in card


@pytest.mark.unit
def test_acceptance_card_verify_fail():
    report = AgentReport(
        headline="开发代理已完成编辑但未通过验证",
        success=False,
        task_id="task_xyz",
        changes=[Change(file="b.py", action="modified", description="")],
        issues=["DEV_VERIFY_GATE: 有编辑但自动验证未通过"],
    )
    attach_delegate_acceptance_meta(
        report,
        role="dev",
        project=type("P", (), {"dev": {"test_command": "pytest"}})(),
        dev_engine={"verify_passed": False, "edits": 1},
    )
    card = format_delegate_acceptance_card(report)
    assert "测试：❌ 未通过" in card


@pytest.mark.unit
def test_acceptance_card_unconfigured_test():
    report = AgentReport(
        headline="开发代理已完成任务",
        success=True,
        task_id="t1",
        changes=[Change(file="c.py", action="created", description="")],
    )
    attach_delegate_acceptance_meta(report, role="dev", project=type("P", (), {"dev": {}})())
    card = format_delegate_acceptance_card(report)
    assert "未配置" in card


@pytest.mark.unit
def test_format_for_wechat_includes_acceptance_card():
    report = AgentReport(
        headline="开发代理已完成任务",
        success=True,
        task_id="t2",
        changes=[Change(file="d.py", action="modified", description="")],
    )
    attach_delegate_acceptance_meta(
        report,
        role="dev",
        project=type("P", (), {"dev": {"test_command": "pytest -q"}})(),
        dev_engine={"verify_passed": True, "edits": 1},
    )
    text = format_for_wechat(report)
    assert "验收卡" in text
    assert "测试：✅ 通过" in text
