"""Sprint 9 audit fix: SEC-9.5 — config_set 入口加 is_gateway_owner 二次校验

Sprint 9 SEC-9.5：butler/tools/config_tools.py:42-49
tool_butler_config(action="set") 任何 Agent 都能调。修复：set 路径在
调 config_set 之前用 is_gateway_owner(platform="wechat", external_id=
chat_id_from_session_key(session_key)) 二次校验；无 session_key 时
fail-closed。list/get/categories 不做 owner 校验（只读）。
"""

from __future__ import annotations

import json

import pytest

from butler.execution_context import use_execution_context
from butler.tools.config_tools import tool_butler_config


@pytest.fixture(autouse=True)
def _owner_env(monkeypatch):
    """默认 u1 是 owner，create_open 不 bypass。"""
    # R1-10: owner check goes through butler.contracts.get_owner_gate();
    # gateway layer wires the real impl at runner startup. Tests must do
    # the same so is_current_turn_owner() can resolve to is_gateway_owner.
    from butler.gateway.gateway_contracts import register_gateway_contracts
    register_gateway_contracts()
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "u1")
    monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)


@pytest.mark.unit
def test_set_rejects_non_owner_session_key():
    """非 owner 调 set 必须返回 ok=False。"""
    with use_execution_context(session_key="wechat:other_user:proj1"):
        result_raw = tool_butler_config(action="set", key="BUTLER_LOG_LEVEL", value="DEBUG")
    result = json.loads(result_raw)

    assert result.get("ok") is False, f"非 owner 不应成功 set: {result!r}"
    assert "owner" in result.get("message", "").lower() or "主公" in result.get("message", ""), (
        f"错误消息应提示 owner 限制: {result.get('message')!r}"
    )


@pytest.mark.unit
def test_set_rejects_when_no_session_key():
    """无 session_key (CLI 单测) → fail-closed。"""
    result_raw = tool_butler_config(action="set", key="BUTLER_LOG_LEVEL", value="DEBUG")
    result = json.loads(result_raw)

    assert result.get("ok") is False, (
        f"无 session_key 不应成功 set: {result!r}"
    )


@pytest.mark.unit
def test_set_allows_owner_session_key(monkeypatch):
    """owner 调 set → 应允许。"""
    monkeypatch.delenv("BUTLER_LOG_LEVEL", raising=False)
    with use_execution_context(session_key="wechat:u1:proj1"):
        result_raw = tool_butler_config(action="set", key="BUTLER_LOG_LEVEL", value="INFO")
    result = json.loads(result_raw)

    assert result.get("ok") is True, f"owner set 应成功: {result!r}"


@pytest.mark.unit
def test_set_allows_when_create_open_bypass(monkeypatch):
    """BUTLER_PROJECT_CREATE_OPEN=1 → 任何 session_key 都可 set（开发模式）。"""
    monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
    with use_execution_context(session_key="wechat:other_user:proj1"):
        result_raw = tool_butler_config(action="set", key="BUTLER_LOG_LEVEL", value="DEBUG")
    result = json.loads(result_raw)

    assert result.get("ok") is True, f"BYPASS 模式 set 应成功: {result!r}"


@pytest.mark.unit
def test_list_action_unaffected_by_owner_gate():
    """list 路径不应被 owner 校验影响 — 任何 session 都能看。"""
    with use_execution_context(session_key="wechat:other_user:proj1"):
        result_raw = tool_butler_config(action="list")
    result = json.loads(result_raw)

    assert result.get("ok") is True, f"非 owner 不应被 list 拒绝: {result!r}"
    assert "items" in result
    assert "count" in result


@pytest.mark.unit
def test_get_action_unaffected_by_owner_gate():
    """get 路径不应被 owner 校验影响。"""
    with use_execution_context(session_key="wechat:other_user:proj1"):
        result_raw = tool_butler_config(action="get", key="BUTLER_LOG_LEVEL")
    result = json.loads(result_raw)

    assert "key" in result, f"非 owner 不应被 get 拒绝: {result!r}"
    assert result.get("key") == "BUTLER_LOG_LEVEL"


@pytest.mark.unit
def test_categories_action_unaffected_by_owner_gate():
    """categories 路径不应被 owner 校验影响。"""
    with use_execution_context(session_key="wechat:other_user:proj1"):
        result_raw = tool_butler_config(action="categories")
    result = json.loads(result_raw)

    assert "categories" in result, f"非 owner 不应被 categories 拒绝: {result!r}"


@pytest.mark.unit
def test_set_rejects_already_protected_keys_for_any_caller():
    """SEC-9.1 移出的 8 key 即使 owner 调 set 也不应成功（双重防御）。"""
    with use_execution_context(session_key="wechat:u1:proj1"):
        result_raw = tool_butler_config(
            action="set", key="BUTLER_IO_GUARDRAIL", value="0"
        )
    result = json.loads(result_raw)

    assert result.get("ok") is False, (
        f"SEC-9.1 保护 key 不应被 set（包括 owner）: {result!r}"
    )


@pytest.mark.unit
def test_set_rejects_when_owner_unset_and_create_open_unset(monkeypatch):
    """owner 与 bypass 都未配置 → fail-closed（与 Sprint 8 SEC-3 一致）。"""
    monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
    monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
    monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
    monkeypatch.delenv("BUTLER_GATEWAY_ALLOWLIST", raising=False)

    with use_execution_context(session_key="wechat:u1:proj1"):
        result_raw = tool_butler_config(action="set", key="BUTLER_LOG_LEVEL", value="DEBUG")
    result = json.loads(result_raw)

    assert result.get("ok") is False, (
        f"无 owner 配置 + 无 bypass + 有 session_key → 应 fail-closed: {result!r}"
    )
