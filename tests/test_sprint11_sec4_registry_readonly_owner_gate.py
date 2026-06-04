"""Sprint 11 SEC-11-4: /技能 搜索/列表/查看 owner gate

Sprint 11 审计：registry_commands.py:109-135 _handle_skills 三个
read-only 子命令（搜索/列表/查看）缺 owner gate，第三方恶意 Skill 描述
喂回 LLM 形成 prompt injection。

修复：
- _handle_skills 顶部加 is_gateway_owner 守门
- 非 Owner 返 owner_required_message()
- Owner 走原有逻辑
- /mcp 不在审计范围（仅 /技能 三子命令被列）

测试：3 个 RED 测试覆盖 搜索/列表/查看 非 Owner 路径 + Owner 仍然通过
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.gateway import registry_commands


@pytest.mark.unit
def test_skills_search_blocked_for_non_owner():
    """/技能 搜索：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=False
    ):
        out = registry_commands.handle_registry_command(
            cmd="/技能",
            arg="搜索 lingwen",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /技能 搜索 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_skills_list_blocked_for_non_owner():
    """/技能 列表：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=False
    ):
        out = registry_commands.handle_registry_command(
            cmd="/技能",
            arg="列表",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /技能 列表 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_skills_inspect_blocked_for_non_owner():
    """/技能 查看：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=False
    ):
        out = registry_commands.handle_registry_command(
            cmd="/技能",
            arg="查看 bundled:demo-skill",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /技能 查看 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_skills_search_passes_through_for_owner():
    """Owner 调 /技能 搜索 应能继续到 svc.search 逻辑。"""
    fake_rec = type("R", (), {"name": "demo", "identifier": "bundled:demo"})()
    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=True
    ), patch("butler.registry.skill_service.SkillRegistryService") as MockSvc:
        svc = MockSvc.return_value
        svc.search.return_value = [fake_rec]
        svc.format_search_table.return_value = "demo | bundled:demo"
        out = registry_commands.handle_registry_command(
            cmd="/技能",
            arg="搜索 lingwen",
            platform="wechat",
            external_id="owner_id",
            session_key="wechat:owner_id:proj",
        )
    assert "demo" in out, f"Owner 应能搜到技能，实际 {out!r}"
    assert svc.search.called, "Owner 应能调到 svc.search"
