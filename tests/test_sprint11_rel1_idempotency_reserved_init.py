"""Sprint 11/14 REL-11-1: `_idempotency_reserved` 提前初始化修复

Sprint 11 审计误判为「提前 init 是死代码」并删除。Sprint 14 复检发现：
- 删除 init 后，idempotency try 块异常时 finally 块 `if _idempotency_reserved:`
  引用未定义变量 → 抛 UnboundLocalError
- UnboundLocalError 阻止 complete_inbound 调用 → inflight 状态永远不释放
  → 后续同 id 消息被误判为重复（假阴性泄漏）

正确修复（不删除 init）：
- 保留 `_idempotency_reserved = False` 在 idempotency try 块**之前**
  （不再放在 bot_loop_guard 块内的旧位置）
- 删除 bot_loop_guard 块内的死 `if _idempotency_reserved: release_inflight`
  （reserve 在它之后才发生）
- 删除 `release_inflight` import（已无引用）
- 保留 try 块内 `_idempotency_reserved = True`（reserve 成功后置位）
- 保留 finally 块 `if _idempotency_reserved: complete_inbound`（有效逻辑）
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from butler.gateway import message_handler


MESSAGE_HANDLER_PATH = Path(message_handler.__file__)


@pytest.mark.unit
def test_idempotency_reserved_false_init_present():
    """`_idempotency_reserved = False` 提前初始化必须保留（防 UnboundLocalError）。

    Sprint 14 复检：Sprint 11 误判 init 为死代码，实际它是 finally 块安全的
    必要条件。删除会导致 idempotency try 块异常时 finally 抛 UnboundLocalError，
    进而阻止 complete_inbound 调用 → inflight 假阴性泄漏。
    """
    text = MESSAGE_HANDLER_PATH.read_text(encoding="utf-8")
    assert "_idempotency_reserved = False" in text, (
        "_idempotency_reserved = False 提前 init **必须保留**：\n"
        "  - finally 块 `if _idempotency_reserved: complete_inbound` 引用它\n"
        "  - 缺少 init → try 块异常时 UnboundLocalError → inflight 假阴性泄漏"
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
