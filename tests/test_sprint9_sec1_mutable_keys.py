"""Sprint 9 audit fix: SEC-9.1 — 8 个安全/dev key 移出 _MUTABLE_KEYS

Sprint 9 SEC-9.1：butler/config_service.py:65-81
_MUTABLE_KEYS 实际注册 5 安全 + 3 dev = 8 key 可被 butler_config 工具
运行时关。修复：把这 8 个 key 的 _register() 调用删掉 → config_set 拒
绝；config_list 不再列；config_get 仍能从 env 读取（向后兼容）。
"""

from __future__ import annotations

import os

import pytest

from butler import config_service as cs


# 全部 8 个 key 列表（5 安全 + 3 dev） — Sprint 9 SEC-9.1 证据
PROTECTED_KEYS: list[tuple[str, str]] = [
    # (key, category)
    ("BUTLER_DOOM_LOOP_THRESHOLD", "安全"),
    ("BUTLER_DOOM_LOOP_MODE", "安全"),
    ("BUTLER_TERMINAL_DANGER_CHECK", "安全"),
    ("BUTLER_IO_GUARDRAIL", "安全"),
    ("BUTLER_READ_BEFORE_EDIT", "安全"),
    ("BUTLER_ENABLE_TERMINAL", "开发"),
    ("BUTLER_ENABLE_GIT_PUSH", "开发"),
    ("BUTLER_EXECUTE_CODE", "开发"),
]


@pytest.mark.unit
@pytest.mark.parametrize("key,category", PROTECTED_KEYS)
def test_config_set_rejects_protected_keys(key, category, monkeypatch):
    """8 个安全/dev key 的 config_set 必须返回 ok=False。"""
    # 关键：先 delenv，确保测试断言的是 config_set 本身有没有写
    monkeypatch.delenv(key, raising=False)
    snapshot_before = dict(os.environ)
    val = "0" if key != "BUTLER_DOOM_LOOP_THRESHOLD" else "5"

    result = cs.config_set(key, val)

    assert result.ok is False, f"{key} 应被 config_set 拒绝（实际 ok=True）"
    assert "不允许" in result.message or "白名单" in result.message, (
        f"{key} 错误消息应提示白名单，实际: {result.message!r}"
    )
    # 关键副作用：config_set 不应写入 os.environ（snapshot 比对）
    assert os.environ == snapshot_before, (
        f"{key} 被拒后 os.environ 仍被改动：差集 "
        f"{set(os.environ.items()) - set(snapshot_before.items())}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("key,category", PROTECTED_KEYS)
def test_config_list_does_not_include_protected_keys(key, category):
    """config_list(category) 不应返回被保护 key。"""
    all_listed = cs.config_list(category)
    listed_keys = {cv.key for cv in all_listed}

    assert key not in listed_keys, f"{key} 不应出现在 config_list({category!r}) 中"


@pytest.mark.unit
def test_config_list_omits_all_protected_keys_when_no_filter():
    """config_list() 无 filter 也不应返回任何被保护 key。"""
    all_listed = cs.config_list()
    listed_keys = {cv.key for cv in all_listed}

    leaked = [k for k, _ in PROTECTED_KEYS if k in listed_keys]
    assert not leaked, f"被保护 key 泄露在 config_list(): {leaked}"


@pytest.mark.unit
@pytest.mark.parametrize("key,category", PROTECTED_KEYS)
def test_config_get_still_reads_env_for_protected_key(key, category, monkeypatch):
    """config_get 仍能从 env 读（向后兼容 — 启动时设的环境变量仍生效）。"""
    monkeypatch.setenv(key, "1" if key != "BUTLER_DOOM_LOOP_THRESHOLD" else "5")

    cv = cs.config_get(key)

    assert cv.key == key
    # 关键：env 有值时，effective 应是 env 的值（meta 可为 None，但 effective 不为空）
    assert cv.effective in ("1", "5", "true", "block", "ask"), (
        f"{key} 应从 env 读出 effective={cv.effective!r}"
    )
    # meta 为 None 是预期（已从 _MUTABLE_KEYS 移出）
    assert cv.meta is None, f"{key} 不再有 meta（移出白名单）"


@pytest.mark.unit
def test_non_protected_keys_still_mutable():
    """非保护 key 仍可正常 set（回归保护）。"""
    result = cs.config_set("BUTLER_LOG_LEVEL", "DEBUG")
    assert result.ok is True
    assert result.message.startswith("BUTLER_LOG_LEVEL 已设为 DEBUG")


@pytest.mark.unit
def test_combo_attack_all_eight_turned_off_at_runtime_fails():
    """5-key combo attack 全部被拒：Sprint 9 SEC-9.1 攻击场景回归测试。"""
    combo = [
        ("BUTLER_IO_GUARDRAIL", "0"),
        ("BUTLER_TERMINAL_DANGER_CHECK", "0"),
        ("BUTLER_DOOM_LOOP_MODE", "ask"),
        ("BUTLER_EXECUTE_CODE", "1"),
        ("BUTLER_ENABLE_GIT_PUSH", "1"),
        ("BUTLER_READ_BEFORE_EDIT", "0"),
    ]
    for key, val in combo:
        result = cs.config_set(key, val)
        assert result.ok is False, f"combo 攻击: {key}={val} 不应成功"


@pytest.mark.unit
def test_total_mutable_keys_decreased_by_eight():
    """_MUTABLE_KEYS 总数减少 8 — 防止有重复注册未清。"""
    # 移出 5 安全 + 3 dev = 8 项后剩 35；后续新增 3 项可写 env（2026-06）
    expected_existing = 38
    actual = len(cs._MUTABLE_KEYS)
    assert actual == expected_existing, (
        f"_MUTABLE_KEYS 期望 {expected_existing} 项（移出 8 个后），"
        f"实际 {actual} 项"
    )
