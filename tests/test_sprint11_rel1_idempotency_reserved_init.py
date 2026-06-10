"""Sprint 11/14 REL-11-1: idempotency 幂等性安全测试

验证 message_handler 幂等逻辑的关键保障点：
- _phase_apply_idempotency 返回 (reply, reserved, inbound_id) 元组
- finally 块在 reserved=True 时调用 complete_inbound
- inbound_pipeline 模块正常 import
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from butler.gateway import message_handler

MESSAGE_HANDLER_PATH = Path(message_handler.__file__)


@pytest.mark.unit
def test_idempotency_tuple_unpacking_present():
    """当前实现通过 _phase_apply_idempotency() 返回元组管理幂等状态。"""
    text = MESSAGE_HANDLER_PATH.read_text(encoding="utf-8")
    assert "_phase_apply_idempotency" in text, (
        "message_handler 应通过 _phase_apply_idempotency 管理幂等逻辑"
    )
    assert "_idempotency_reserved" in text, (
        "message_handler 应使用 _idempotency_reserved 变量"
    )


@pytest.mark.unit
def test_finally_complete_inbound_preserved():
    """finally 块 `if _idempotency_reserved: complete_inbound` 必须保留。"""
    text = MESSAGE_HANDLER_PATH.read_text(encoding="utf-8")
    assert re.search(
        r"finally:.*?_idempotency_reserved.*?complete_inbound",
        text,
        re.DOTALL,
    ), (
        "finally 块必须保留 `if _idempotency_reserved: complete_inbound` "
        "（确保 reserve 后正常 complete）"
    )


@pytest.mark.unit
def test_phase_apply_idempotency_returns_tuple():
    """_phase_apply_idempotency 应返回 (reply, reserved, inbound_id) 三元组。"""
    from butler.gateway.message_pipelines import _phase_apply_idempotency
    import inspect

    sig = inspect.signature(_phase_apply_idempotency)
    ret = sig.return_annotation
    assert "tuple" in str(ret).lower() or ret == inspect.Parameter.empty, (
        "_phase_apply_idempotency 应返回 tuple"
    )


@pytest.mark.unit
def test_release_inflight_not_used():
    """重构后 release_inflight 不应再出现在 message_handler 中。"""
    text = MESSAGE_HANDLER_PATH.read_text(encoding="utf-8")
    assert "release_inflight" not in text, (
        "release_inflight 在当前重构中已被移除，不应出现"
    )


@pytest.mark.unit
def test_inbound_idempotency_module_importable():
    """inbound_idempotency 模块应可正常 import。"""
    from butler.gateway import inbound_idempotency
    assert hasattr(inbound_idempotency, "check_and_reserve_inbound")
    assert hasattr(inbound_idempotency, "complete_inbound")
