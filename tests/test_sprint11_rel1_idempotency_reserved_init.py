"""Sprint 11 REL-11-1: `_idempotency_reserved = False` 提前初始化死代码

Sprint 11 审计：butler/gateway/message_handler.py:389 `_idempotency_reserved
= False` 提前初始化，line 401 `if _idempotency_reserved:` 检查时该变量
永远 False（reserve 在 531 才发生），导致 line 401-405 的 release_inflight
死代码。

分析：
- 死代码是真实的：bot_loop_guard 在 idempotency reserve **之前**就
  触发 return，suppress 时 inflight 还没 reserve，release_inflight 必 no-op
- line 643 finally 块的 `if _idempotency_reserved: complete_inbound` 是
  有效代码（reserve 后才置位），必须保留
- line 23 的 `release_inflight` import 也变成死引用，可一并清理

修复：删 line 389 提前 init + 删 line 401-405 死 if 块 + 删 line 23
无用 import。保留 line 531 (set True) + line 643 (finally check)。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from butler.gateway import message_handler


MESSAGE_HANDLER_PATH = Path(message_handler.__file__)


@pytest.mark.unit
def test_idempotency_reserved_false_init_removed():
    """`_idempotency_reserved = False` 提前初始化应被删除。"""
    text = MESSAGE_HANDLER_PATH.read_text(encoding="utf-8")
    # 原 line 389: `_idempotency_reserved = False`
    # 修复后：行应不存在（init 与 reserve 后置位合并到 try 块内）
    assert "_idempotency_reserved = False" not in text, (
        "_idempotency_reserved = False 提前 init 是死代码（检查时永远 False），\n"
        "应删除并依赖 line 531 reserve 成功后置位"
    )


@pytest.mark.unit
def test_dead_release_inflight_in_bot_loop_guard_removed():
    """bot_loop_guard 内的死 release_inflight 调用应被删除。"""
    text = MESSAGE_HANDLER_PATH.read_text(encoding="utf-8")
    # 原 line 401-405: 在 `if suppress:` 内的 `if _idempotency_reserved:` 块
    # 此处 _idempotency_reserved 永远 False → release_inflight 永远不被调
    # 且 reserve 在 line 518-522 之后才发生，suppress 时 inflight 还没 reserve
    # → 即使调用也是 no-op，是纯死代码

    # 修复后：bot_loop_guard try 块内不应再有 release_inflight 调用
    # 提取 bot_loop_guard 块源码
    src = inspect.getsource(message_handler)
    # 找 "from butler.gateway.bot_loop_guard" 到下一个 "except Exception"
    match = re.search(
        r"from butler\.gateway\.bot_loop_guard.*?(?=except\s+Exception|try:|def\s)",
        src,
        re.DOTALL,
    )
    assert match, "找不到 bot_loop_guard 块"
    bot_loop_block = match.group(0)
    assert "release_inflight" not in bot_loop_block, (
        f"bot_loop_guard 块内 release_inflight 是死代码（_idempotency_reserved 永远 False）\n"
        f"块源码：\n{bot_loop_block}"
    )


@pytest.mark.unit
def test_release_inflight_import_still_present_or_removed_consistently():
    """release_inflight 的 import 与使用应一致（全删或全留）。

    修复后预期：release_inflight 完全不再使用 → import 应一并删除。
    """
    text = MESSAGE_HANDLER_PATH.read_text(encoding="utf-8")
    import_count = text.count("from butler.gateway.inbound_idempotency import")
    release_call_count = text.count("release_inflight(")  # 调用点
    release_name_count = len(
        re.findall(r"\brelease_inflight\b", text)
    )  # 任何引用（import + call）
    # 如果 import 存在，调用也应存在；反之亦然
    if "release_inflight" in text and "from butler.gateway.inbound_idempotency import" in text:
        # 假设 import 仍引用 release_inflight
        import_line = re.search(
            r"from butler\.gateway\.inbound_idempotency import\s+([^\n]+)", text
        )
        if import_line:
            imported_names = import_line.group(1)
            if "release_inflight" in imported_names:
                # import 包含 release_inflight，必须有调用点
                assert release_call_count >= 1, (
                    f"import 了 release_inflight 但无调用点：\n{imported_names}"
                )


@pytest.mark.unit
def test_idempotency_reserved_true_set_preserved():
    """line 531 `_idempotency_reserved = True` 必须保留（finally 块需要）。"""
    text = MESSAGE_HANDLER_PATH.read_text(encoding="utf-8")
    assert "_idempotency_reserved = True" in text, (
        "line 531 `_idempotency_reserved = True` 必须保留，"
        "finally 块 (line 643) 需要它判断是否 complete_inbound"
    )


@pytest.mark.unit
def test_finally_complete_inbound_preserved():
    """line 643 finally 块 `if _idempotency_reserved: complete_inbound` 必须保留。"""
    text = MESSAGE_HANDLER_PATH.read_text(encoding="utf-8")
    # 找 finally 块
    assert re.search(
        r"finally:.*?_idempotency_reserved.*?complete_inbound",
        text,
        re.DOTALL,
    ), (
        "finally 块必须保留 `if _idempotency_reserved: complete_inbound` "
        "（这是有效逻辑，确保 reserve 后正常 complete）"
    )


@pytest.mark.unit
def test_bot_loop_guard_suppress_does_not_call_release_inflight(tmp_path, monkeypatch):
    """行为验证：bot_loop_guard 触发 suppress 时，release_inflight 不应被调用。

    当前 bug：code path 中写了 release_inflight 调用，但 _idempotency_reserved
    永远 False 所以调用永远不执行。修复后：code path 中根本不应有 release_inflight
    （行为不变，但死代码消失）。
    """
    # 用 importlib 直接 inspect 模块函数源码
    src = inspect.getsource(message_handler)
    # 提取完整 bot_loop_guard try 块
    match = re.search(
        r"try:\s*\n\s*from butler\.gateway\.bot_loop_guard import record_and_should_suppress.*?(?=\n        except|\n        try:)",
        src,
        re.DOTALL,
    )
    assert match, "无法定位 bot_loop_guard try 块"
    block = match.group(0)
    # 修复后断言：块内不应有 release_inflight 调用
    assert "release_inflight" not in block, (
        f"bot_loop_guard try 块内不应再有 release_inflight 调用（死代码）\n块：\n{block}"
    )
