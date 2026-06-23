# P1-3.1 Turn-Based Compaction `/诊断` 可见策略 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `/诊断` 能看见本轮压缩采用了 turn / split_turn / legacy_split / no_op 哪种策略，通过 always-on 的 6 字段 diagnostic 注入到 `select_tail_start_index` / `split_head_tail_turns` / `compress_messages` / `try_reactive_compact`。

**Architecture:** `select_tail_start_index` 加 `diagnostics: dict | None = None` kw-only 形参，函数末尾按真实执行状态写入 6 字段。`split_head_tail_turns` / `compress_messages` / `try_reactive_compact` 透传。算法本身、env toggle、`/诊断` 渲染均不动。Fallback (`legacy_split`) 由调用方在 try/except 直接写入。

**Tech Stack:** Python 3.13, pytest, dataclass, AST-free 纯 dict 写入。已有 `turn_compaction.py` (253 行) + 7 个测试 + `context_compressor.py` (407 行) + `reactive_compact.py`。

**Spec:** `docs/plans/archive/superpowers/specs/2026-06-04-p1-3-1-turn-based-compaction-diagnostics-design.md`

---

## File Structure

| File | 角色 | 改动 |
|------|------|------|
| `butler/core/turn_compaction.py` | 算法 + 写入点 | 加 `_strategy_label` helper, `select_tail_start_index` 加 diagnostics 形参, `split_head_tail_turns` 透传 |
| `butler/core/context_compressor.py` | 上层入口 | `compress_messages` 透传 diagnostics, except 路径写 `legacy_split` |
| `butler/core/reactive_compact.py` | reactive 路径 | `try_reactive_compact` 加 diagnostics 形参, turn-mode 成功时写 strategy |
| `tests/test_turn_compaction.py` | 测试 | 新增 6 个测试覆盖 diagnostic dict 行为 |

不改任何 `/诊断` 渲染代码、env toggle、算法逻辑。

---

## Task 1: 加 `_strategy_label` helper

**Files:**
- Modify: `butler/core/turn_compaction.py:1-15` (imports + 新 helper)

- [ ] **Step 1: 在 turn_compaction.py 顶部 import 区域加 `Any` 并新增 `_strategy_label` helper**

修改 `butler/core/turn_compaction.py` 第 8 行附近：

```python
from typing import Any, Callable
```

在 `_SUMMARY_MARKERS` 之后（第 22 行附近），新增：

```python
def _strategy_label(
    tail_turns_kept: int,
    split_applied: bool,
    middle_present: bool,
) -> str:
    """Generate human-readable compaction strategy tag for /诊断 output."""
    if not middle_present:
        return "no_op"
    base = f"turns:{tail_turns_kept}"
    return f"{base}+split" if split_applied else base
```

- [ ] **Step 2: 运行已有测试确认无回归**

Run: `pytest tests/test_turn_compaction.py -v`
Expected: 7/7 PASS (helper 未被调用, 只是添加)

- [ ] **Step 3: Commit**

```bash
git add butler/core/turn_compaction.py
git commit -m "feat(turn_compaction): add _strategy_label helper for /诊断"
```

---

## Task 2: 写 RED 测试 - `test_diagnostics_strategy_turns_2`

**Files:**
- Modify: `tests/test_turn_compaction.py:1-25` (imports)

- [ ] **Step 1: 在 test_turn_compaction.py 顶部 import `_strategy_label`**

```python
from butler.core.turn_compaction import (
    _strategy_label,
    append_overflow_replay,
    find_overflow_replay_user,
    group_messages_into_turns,
    preserve_recent_token_budget,
    select_tail_start_index,
    split_head_tail_turns,
)
```

- [ ] **Step 2: 写失败的测试 - 验证 8 turn 场景写入 `turns:2` strategy**

在 `test_preserve_recent_budget_clamped` 之后新增：

```python
@pytest.mark.unit
def test_diagnostics_strategy_turns_2():
    """8 turn 场景 → compaction_strategy='turns:2', tail_turns_kept=2."""
    rest: list[dict] = []
    for i in range(8):
        rest.append({"role": "user", "content": f"u-{i}"})
        rest.append({"role": "assistant", "content": f"a-{i}" * 50})
    diag: dict = {}
    start = select_tail_start_index(
        rest,
        max_context_tokens=128_000,
        tail_turns=2,
        split_turn=False,
        diagnostics=diag,
    )
    assert start > 0
    assert diag["compaction_strategy"] == "turns:2"
    assert diag["compaction_tail_turns_kept"] == 2
    assert diag["compaction_split_turn_applied"] is False
    assert isinstance(diag["compaction_preserved_recent_budget"], int)
    assert diag["compaction_tail_token_count"] > 0
    assert diag["compaction_tail_start_index"] == start
```

- [ ] **Step 3: 运行测试, 确认 RED (因 select_tail_start_index 还不接受 diagnostics 形参)**

Run: `pytest tests/test_turn_compaction.py::test_diagnostics_strategy_turns_2 -v`
Expected: FAIL with `TypeError: select_tail_start_index() got an unexpected keyword argument 'diagnostics'`

- [ ] **Step 4: Commit RED**

```bash
git add tests/test_turn_compaction.py
git commit -m "test(turn_compaction): RED test_diagnostics_strategy_turns_2"
```

---

## Task 3: GREEN - 给 `select_tail_start_index` 加 diagnostics 形参

**Files:**
- Modify: `butler/core/turn_compaction.py:122-172` (function signature + body)

- [ ] **Step 1: 改 `select_tail_start_index` 签名加 `diagnostics: dict | None = None`**

修改第 122-130 行：

```python
def select_tail_start_index(
    rest: list[dict],
    *,
    max_context_tokens: int,
    max_output_tokens: int | None = None,
    tail_turns: int | None = None,
    split_turn: bool | None = None,
    estimate_fn: Callable[[list[dict]], int] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> int:
```

- [ ] **Step 2: 改函数体追踪状态 (split_applied + total_kept_turns), 函数末尾写 diagnostics**

完整替换 `select_tail_start_index` 函数体（第 131-172 行）：

```python
    """
    Return index in ``rest`` where preserved tail begins.
    ``0`` means entire ``rest`` is kept (no middle to compact).
    """
    limit = tail_turns if tail_turns is not None else tail_turns_limit()
    if limit <= 0 or not rest:
        if diagnostics is not None:
            diagnostics["compaction_strategy"] = "no_op"
            diagnostics["compaction_tail_turns_kept"] = 0
            diagnostics["compaction_split_turn_applied"] = False
            diagnostics["compaction_preserved_recent_budget"] = 0
            diagnostics["compaction_tail_token_count"] = 0
            diagnostics["compaction_tail_start_index"] = 0
        return 0

    turns = group_messages_into_turns(rest)
    if not turns:
        if diagnostics is not None:
            diagnostics["compaction_strategy"] = "no_op"
            diagnostics["compaction_tail_turns_kept"] = 0
            diagnostics["compaction_split_turn_applied"] = False
            diagnostics["compaction_preserved_recent_budget"] = 0
            diagnostics["compaction_tail_token_count"] = 0
            diagnostics["compaction_tail_start_index"] = 0
        return 0

    budget = preserve_recent_token_budget(
        max_context_tokens,
        max_output_tokens=max_output_tokens,
    )
    recent = turns[-limit:]
    total = 0
    keep_start: int | None = None
    kept_turn_count = 0
    do_split = split_turn_enabled() if split_turn is None else split_turn
    split_applied = False

    for turn in reversed(recent):
        chunk = rest[turn.start : turn.end]
        size = _estimate_messages_tokens(chunk, estimate_fn)
        if total + size <= budget:
            total += size
            keep_start = turn.start
            kept_turn_count += 1
            continue
        remaining = budget - total
        if do_split and remaining > 0:
            split = _split_turn_suffix(rest, turn, budget=remaining, estimate_fn=estimate_fn)
            if split is not None:
                keep_start = split.start
                split_applied = True
            elif keep_start is None:
                keep_start = turn.start
                kept_turn_count = 1
        elif keep_start is None:
            keep_start = turn.start
            kept_turn_count = 1
        break

    if keep_start is None:
        kept_turn_count = len(recent)
        if diagnostics is not None:
            diagnostics["compaction_strategy"] = _strategy_label(
                kept_turn_count, split_applied, middle_present=True
            )
            diagnostics["compaction_tail_turns_kept"] = kept_turn_count
            diagnostics["compaction_split_turn_applied"] = split_applied
            diagnostics["compaction_preserved_recent_budget"] = budget
            diagnostics["compaction_tail_token_count"] = total
            diagnostics["compaction_tail_start_index"] = 0
        return 0

    if keep_start <= 0:
        if diagnostics is not None:
            diagnostics["compaction_strategy"] = _strategy_label(
                kept_turn_count, split_applied, middle_present=True
            )
            diagnostics["compaction_tail_turns_kept"] = kept_turn_count
            diagnostics["compaction_split_turn_applied"] = split_applied
            diagnostics["compaction_preserved_recent_budget"] = budget
            diagnostics["compaction_tail_token_count"] = total
            diagnostics["compaction_tail_start_index"] = 0
        return 0

    if diagnostics is not None:
        diagnostics["compaction_strategy"] = _strategy_label(
            kept_turn_count, split_applied, middle_present=True
        )
        diagnostics["compaction_tail_turns_kept"] = kept_turn_count
        diagnostics["compaction_split_turn_applied"] = split_applied
        diagnostics["compaction_preserved_recent_budget"] = budget
        diagnostics["compaction_tail_token_count"] = total
        diagnostics["compaction_tail_start_index"] = keep_start
    return keep_start
```

- [ ] **Step 3: 运行 Task 2 测试 + 既有 7 个测试**

Run: `pytest tests/test_turn_compaction.py -v`
Expected: 8/8 PASS (1 new + 7 existing)

- [ ] **Step 4: Commit GREEN**

```bash
git add butler/core/turn_compaction.py tests/test_turn_compaction.py
git commit -m "feat(turn_compaction): select_tail_start_index 写 6 字段 diagnostics"
```

---

## Task 4: RED - `test_diagnostics_strategy_turns_2_split`

**Files:**
- Modify: `tests/test_turn_compaction.py` (after Task 2's test)

- [ ] **Step 1: 写失败的测试 - 验证单 turn 超大触发 split**

```python
@pytest.mark.unit
def test_diagnostics_strategy_turns_2_split():
    """单个超大 turn 触发 mid-turn split → 'turns:2+split'."""
    big = "x" * 8000
    rest = [
        {"role": "user", "content": "start"},
        {"role": "assistant", "content": big},
        {"role": "assistant", "content": "short tail reply"},
    ]
    diag: dict = {}
    start = select_tail_start_index(
        rest,
        max_context_tokens=12_000,
        tail_turns=1,
        split_turn=True,
        diagnostics=diag,
    )
    assert start == 2
    assert diag["compaction_strategy"] == "turns:1+split"
    assert diag["compaction_split_turn_applied"] is True
    assert diag["compaction_tail_turns_kept"] == 1
    assert diag["compaction_tail_start_index"] == start
```

- [ ] **Step 2: 运行测试, 确认 PASS (Task 3 已实现)**

Run: `pytest tests/test_turn_compaction.py::test_diagnostics_strategy_turns_2_split -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_turn_compaction.py
git commit -m "test(turn_compaction): test_diagnostics_strategy_turns_2_split"
```

---

## Task 5: RED - `test_diagnostics_no_op_when_few_messages`

**Files:**
- Modify: `tests/test_turn_compaction.py` (after Task 4's test)

- [ ] **Step 1: 写失败的测试 - 验证 4 turn ≤ 阈值时 'no_op'**

```python
@pytest.mark.unit
def test_diagnostics_no_op_when_few_messages():
    """4 turn (≤ head + min_tail=2) → no_op, tail_start=0."""
    rest: list[dict] = []
    for i in range(4):
        rest.append({"role": "user", "content": f"u-{i}"})
        rest.append({"role": "assistant", "content": f"a-{i}"})
    diag: dict = {}
    # Note: select_tail_start_index doesn't know about head+min_tail, but with 4 turns
    # and tight budget the algorithm should produce a tail_start > 0; for "no_op" we
    # use the full-function path via split_head_tail_turns.
    system, middle, head_tail = split_head_tail_turns(
        rest,
        max_context_tokens=128_000,
        head_count=3,
        min_tail_messages=4,
        diagnostics=diag,
    )
    assert middle == []
    assert diag["compaction_strategy"] == "no_op"
    assert diag["compaction_tail_start_index"] == 0
```

- [ ] **Step 2: 运行测试, 确认 RED (split_head_tail_turns 还不接受 diagnostics)**

Run: `pytest tests/test_turn_compaction.py::test_diagnostics_no_op_when_few_messages -v`
Expected: FAIL with `TypeError: split_head_tail_turns() got an unexpected keyword argument 'diagnostics'`

- [ ] **Step 3: Commit RED**

```bash
git add tests/test_turn_compaction.py
git commit -m "test(turn_compaction): RED test_diagnostics_no_op_when_few_messages"
```

---

## Task 6: GREEN - `split_head_tail_turns` 加 diagnostics 透传

**Files:**
- Modify: `butler/core/turn_compaction.py:175-210` (function signature + body)

- [ ] **Step 1: 改 `split_head_tail_turns` 签名加 diagnostics kw-only 形参**

修改第 175-183 行：

```python
def split_head_tail_turns(
    messages: list[dict],
    *,
    max_context_tokens: int,
    max_output_tokens: int | None = None,
    head_count: int = 3,
    min_tail_messages: int = 4,
    estimate_fn: Callable[[list[dict]], int] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
```

- [ ] **Step 2: 改函数体透传 diagnostics 给 select_tail_start_index**

修改第 193-198 行：

```python
    tail_start = select_tail_start_index(
        body,
        max_context_tokens=max_context_tokens,
        max_output_tokens=max_output_tokens,
        estimate_fn=estimate_fn,
        diagnostics=diagnostics,
    )
```

保持函数其余部分不变（return tuples 不变）。

- [ ] **Step 3: 运行 Task 5 测试 + 既有 8 个测试**

Run: `pytest tests/test_turn_compaction.py -v`
Expected: 10/10 PASS (1 new + 1 new + 1 new + 7 existing)

- [ ] **Step 4: Commit**

```bash
git add butler/core/turn_compaction.py tests/test_turn_compaction.py
git commit -m "feat(turn_compaction): split_head_tail_turns 透传 diagnostics"
```

---

## Task 7: RED - `test_diagnostics_via_compress_messages` (end-to-end)

**Files:**
- Modify: `tests/test_turn_compaction.py` (after Task 5's test)

- [ ] **Step 1: 写失败的端到端测试 - 验证 compress_messages 透传**

```python
@pytest.mark.unit
def test_diagnostics_via_compress_messages():
    """端到端: compress_messages(messages, diagnostics={}) → dict 含 6 字段."""
    messages: list[dict] = [{"role": "system", "content": "sys"}]
    for i in range(8):
        messages.append({"role": "user", "content": f"u-{i}"})
        messages.append({"role": "assistant", "content": f"a-{i}" * 80})

    diag: dict = {}
    with patch(
        "butler.core.context_compressor.auxiliary_complete",
        return_value="## Active Task\n- done",
    ):
        out, _, did = compress_messages(
            messages,
            max_tokens=4000,
            threshold_ratio=0.01,
            min_messages_to_compress=4,
            diagnostics=diag,
        )
    assert did
    assert "compaction_strategy" in diag
    assert diag["compaction_strategy"].startswith("turns:")
    assert "compaction_tail_turns_kept" in diag
    assert isinstance(diag["compaction_tail_turns_kept"], int)
```

- [ ] **Step 2: 运行测试, 确认 RED (compress_messages diagnostics 还没透传)**

Run: `pytest tests/test_turn_compaction.py::test_diagnostics_via_compress_messages -v`
Expected: FAIL - assertion `diag["compaction_strategy"]` KeyError or "turns:" not in

- [ ] **Step 3: Commit RED**

```bash
git add tests/test_turn_compaction.py
git commit -m "test(turn_compaction): RED test_diagnostics_via_compress_messages"
```

---

## Task 8: GREEN - `compress_messages` 透传 diagnostics

**Files:**
- Modify: `butler/core/context_compressor.py:265-298` (turn_compaction_enabled block)

- [ ] **Step 1: 改 `compress_messages` 调用 `split_head_tail_turns` 时透传 diagnostics**

修改 `butler/core/context_compressor.py` 第 265-275 行：

```python
        if turn_compaction_enabled():
            system, middle, head_tail = split_head_tail_turns(
                pruned,
                max_context_tokens=max_tokens,
                max_output_tokens=max_output_tokens,
                head_count=head_count,
                min_tail_messages=min_tail_messages,
                estimate_fn=_estimate_tokens,
                diagnostics=diagnostics,
            )
```

- [ ] **Step 2: 在 except 块直接写 `compaction_strategy = "legacy_split"`**

修改第 298-305 行（except 块）：

```python
    except Exception as exc:
        logger.debug("Turn compaction fallback: %s", exc)
        if isinstance(diagnostics, dict):
            diagnostics["compaction_strategy"] = "legacy_split"
            diagnostics["compaction_tail_turns_kept"] = 0
            diagnostics["compaction_split_turn_applied"] = False
            diagnostics["compaction_preserved_recent_budget"] = 0
            diagnostics["compaction_tail_token_count"] = 0
            diagnostics["compaction_tail_start_index"] = 0
        system, middle, head_tail = _split_head_tail(
            pruned,
            head_count=head_count,
            max_tail_messages=max_tail_messages,
            min_tail_messages=min_tail_messages,
        )
```

- [ ] **Step 3: 运行 Task 7 测试 + 既有 10 个测试**

Run: `pytest tests/test_turn_compaction.py -v`
Expected: 11/11 PASS (1 new + 1 new + 1 new + 1 new + 7 existing)

- [ ] **Step 4: Commit**

```bash
git add butler/core/context_compressor.py tests/test_turn_compaction.py
git commit -m "feat(context_compressor): 透传 diagnostics + legacy_split fallback 写入"
```

---

## Task 9: RED - `test_diagnostics_no_op_when_none` (None safety)

**Files:**
- Modify: `tests/test_turn_compaction.py` (after Task 7's test)

- [ ] **Step 1: 写失败的测试 - 验证 diagnostics=None 仍能正常返回**

```python
@pytest.mark.unit
def test_diagnostics_no_op_when_none():
    """diagnostics=None 时 select_tail_start_index 仍能正常返回 (不抛错)."""
    rest: list[dict] = []
    for i in range(6):
        rest.append({"role": "user", "content": f"u-{i}"})
        rest.append({"role": "assistant", "content": f"a-{i}" * 50})
    # No diagnostics kwarg → uses default None
    start = select_tail_start_index(
        rest,
        max_context_tokens=128_000,
        tail_turns=2,
    )
    assert isinstance(start, int)
    assert start >= 0
```

- [ ] **Step 2: 运行测试, 确认 PASS (已有行为, 7 个旧测试覆盖)**

Run: `pytest tests/test_turn_compaction.py::test_diagnostics_no_op_when_none -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_turn_compaction.py
git commit -m "test(turn_compaction): test_diagnostics_no_op_when_none"
```

---

## Task 10: RED - `test_diagnostics_legacy_fallback_on_exception`

**Files:**
- Modify: `tests/test_turn_compaction.py` (after Task 9's test)

- [ ] **Step 1: 写失败的测试 - 验证 turn_compaction 抛异常时写 `legacy_split`**

```python
@pytest.mark.unit
def test_diagnostics_legacy_fallback_on_exception():
    """turn_compaction 抛异常时 diagnostics 写 'legacy_split' + 兼容原 fallback 标记."""
    messages: list[dict] = [{"role": "system", "content": "sys"}]
    for i in range(8):
        messages.append({"role": "user", "content": f"u-{i}"})
        messages.append({"role": "assistant", "content": f"a-{i}" * 80})

    diag: dict = {}
    # Force split_head_tail_turns to raise; compress_messages catches → fallback
    with patch(
        "butler.core.turn_compaction.split_head_tail_turns",
        side_effect=RuntimeError("boom"),
    ):
        with patch(
            "butler.core.context_compressor.auxiliary_complete",
            return_value="## Active Task\n- ok",
        ):
            out, _, did = compress_messages(
                messages,
                max_tokens=4000,
                threshold_ratio=0.01,
                min_messages_to_compress=4,
                diagnostics=diag,
            )
    assert did
    assert diag.get("compaction_strategy") == "legacy_split"
    assert diag.get("compaction_turn_fallback") == "legacy_split"
```

- [ ] **Step 2: 运行测试, 确认 PASS (Task 8 已实现) 或 RED (若 mock 路径需调整)**

Run: `pytest tests/test_turn_compaction.py::test_diagnostics_legacy_fallback_on_exception -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_turn_compaction.py
git commit -m "test(turn_compaction): test_diagnostics_legacy_fallback_on_exception"
```

---

## Task 11: RED - `test_diagnostics_reactive_compact_turns`

**Files:**
- Modify: `tests/test_reactive_compact.py` (or new file)

- [ ] **Step 1: 检查是否已有 test_reactive_compact.py**

Run: `ls tests/test_reactive_compact.py 2>&1`
Expected: file exists (从之前 grep 看到 1242 passed 中有它)

- [ ] **Step 2: 写失败的测试 - 验证 try_reactive_compact turn-mode 写 strategy**

在 `tests/test_reactive_compact.py` 末尾新增：

```python
def test_reactive_compact_turn_mode_writes_strategy(monkeypatch):
    """try_reactive_compact turn-mode 成功时写 compaction_strategy='turns:N' + reactive_compact_strategy."""
    from butler.core.reactive_compact import try_reactive_compact
    from butler.core.context_compressor import compress_messages  # noqa: F401
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(10):
        msgs.append({"role": "user", "content": f"u-{i}"})
        msgs.append({"role": "assistant", "content": f"a-{i}" * 60})
    diag: dict = {}
    def fake_compress(messages: list[dict]) -> list[dict]:
        return [{"role": "system", "content": "ok"}]
    ok, new_msgs, reason = try_reactive_compact(
        msgs, compress_fn=fake_compress, use_turn_tail=True, diagnostics=diag
    )
    assert ok is True
    assert reason == "ok"
    assert diag.get("compaction_strategy", "").startswith("turns:")
    assert "reactive_compact_strategy" in diag
```

- [ ] **Step 3: 运行测试, 确认 RED (try_reactive_compact 还不接受 diagnostics)**

Run: `pytest tests/test_reactive_compact.py::test_reactive_compact_turn_mode_writes_strategy -v`
Expected: FAIL with `TypeError: try_reactive_compact() got an unexpected keyword argument 'diagnostics'`

- [ ] **Step 4: Commit RED**

```bash
git add tests/test_reactive_compact.py
git commit -m "test(reactive_compact): RED test_reactive_compact_turn_mode_writes_strategy"
```

---

## Task 12: GREEN - `try_reactive_compact` 加 diagnostics 形参

**Files:**
- Modify: `butler/core/reactive_compact.py:35-75` (try_reactive_compact function)

- [ ] **Step 1: 改 `try_reactive_compact` 签名加 diagnostics kw-only 形参**

修改 `butler/core/reactive_compact.py` 第 33-46 行：

```python
def try_reactive_compact(
    messages: list[dict],
    *,
    compress_fn: Callable[[list[dict]], list[dict]],
    min_rounds_to_drop: int = 1,
    max_rounds_to_drop: int = 3,
    use_turn_tail: bool = True,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[bool, list[dict], str]:
```

- [ ] **Step 2: turn-mode 成功时写 strategy 字段**

修改第 50-73 行的 turn-mode 分支：

```python
    if use_turn_tail:
        try:
            from butler.core.turn_compaction import (
                group_messages_into_turns,
                turn_compaction_enabled,
            )

            if turn_compaction_enabled():
                system_msgs = [m for m in messages if m.get("role") == "system"]
                rest = [m for m in messages if m.get("role") != "system"]
                turns = group_messages_into_turns(rest)
                if len(turns) <= min_rounds_to_drop + 1:
                    return False, messages, "too_few_turns"
                keep_turns = turns[-max(1, len(turns) - max_rounds_to_drop) :]
                tail_start = keep_turns[0].start
                flattened = list(system_msgs[:1]) + rest[tail_start:]
                try:
                    compressed = _compress_with_overflow_replay(compress_fn, flattened)
                except Exception as exc:
                    logger.warning("Reactive compact failed: %s", exc)
                    return False, messages, "error"
                if len(compressed) >= len(messages):
                    return False, messages, "exhausted"
                if diagnostics is not None:
                    strategy = f"turns:{len(keep_turns)}"
                    diagnostics["compaction_strategy"] = strategy
                    diagnostics["reactive_compact_strategy"] = strategy
                return True, compressed, "ok"
        except Exception as exc:
            logger.debug("try reactive compact skipped: %s", exc)
```

- [ ] **Step 3: 运行 Task 11 测试 + 既有 reactive tests**

Run: `pytest tests/test_reactive_compact.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add butler/core/reactive_compact.py tests/test_reactive_compact.py
git commit -m "feat(reactive_compact): try_reactive_compact turn-mode 写 strategy"
```

---

## Task 13: 全量回归 + 验收

- [ ] **Step 1: 运行所有 turn/context/reactive 测试**

Run: `pytest tests/test_turn_compaction.py tests/test_context_compressor.py tests/test_reactive_compact.py -v`
Expected: 全过 (turn=13, compressor 已有, reactive 新增 1)

- [ ] **Step 2: 运行全量测试, 确认无回归**

Run: `PYTHONPATH=. pytest tests/ -q --timeout=60 2>&1 | tail -20`
Expected: 1242 passed + 6 new + 1 new = 1249 passed (or 0 failed). Pre-existing failures 应保持不变。

- [ ] **Step 3: 手动端到端验证 /诊断 输出**

模拟一次压缩, 检查 diagnostics dict 真实写入 6 字段:

```bash
python -c "
import sys
sys.path.insert(0, '.')
from butler.core.turn_compaction import split_head_tail_turns
msgs = [{'role': 'system', 'content': 'sys'}]
for i in range(8):
    msgs.append({'role': 'user', 'content': f'u-{i}'})
    msgs.append({'role': 'assistant', 'content': f'a-{i}' * 60})
diag = {}
sys_, mid, head_tail = split_head_tail_turns(msgs, max_context_tokens=4000, diagnostics=diag)
print('strategy:', diag.get('compaction_strategy'))
print('tail_turns_kept:', diag.get('compaction_tail_turns_kept'))
print('split_applied:', diag.get('compaction_split_turn_applied'))
print('tail_start:', diag.get('compaction_tail_start_index'))
"
```

Expected output:
```
strategy: turns:2
tail_turns_kept: 2
split_applied: False
tail_start: <int>
```

- [ ] **Step 4: Commit (如有改动)**

```bash
git status
# 如果无新文件改动, 跳过
git log --oneline -1
```

---

## Task 14: 标记 opencode §3.1 完成

**Files:**
- Modify: `docs/plans/active/opencode-actionable-optimization-checklist-2026-05.md:43-58` (§3.1 章节)

- [ ] **Step 1: 把 §3.1 三个 checkbox 改为 [x], 标完成日期与 commit**

修改 `docs/plans/active/opencode-actionable-optimization-checklist-2026-05.md` 第 43-58 行的 `- [ ]` 改为 `- [x]`, 并在章节末加:

```markdown
> **Sprint 24 (2026-06-04) 完成**: 加 `_strategy_label` helper + `select_tail_start_index` diagnostics 注入, 6 字段 always-on (`compaction_strategy` / `tail_turns_kept` / `split_turn_applied` / `preserved_recent_budget` / `tail_token_count` / `tail_start_index`); 6 新测试覆盖 strategy 标签生成 / 透传 / fallback / no_op / end-to-end. 1242 passed 无回归.
```

- [ ] **Step 2: Commit**

```bash
git add docs/plans/active/opencode-actionable-optimization-checklist-2026-05.md
git commit -m "docs: opencode §3.1 标记为完成 (turn-based compaction /诊断 可见策略)"
```

---

## Self-Review

**1. Spec coverage:**
- §1.3 (只动诊断可见性) — Task 1-12 全部只改 diagnostics 注入, 不动算法
- §2.1 (写入点选 A) — Task 3 实施
- §2.2 (6 字段) — Task 3 实施
- §2.3 (策略标签生成) — Task 1 helper + Task 3 调用
- §2.4 (fallback 标记) — Task 8 except 块
- §3.1 (turn_compaction.py 改) — Task 1, 3, 6
- §3.2 (context_compressor.py 改) — Task 8
- §3.3 (reactive_compact.py 改) — Task 12
- §3.4 (test_turn_compaction.py 新增 6 测试) — Task 2, 4, 5, 7, 9, 10
- §4.2 (6 测试名称) — Task 2, 4, 5, 7, 9, 10
- §5.1 (签名兼容性) — kw-only 形参默认 None
- §5.2 (行为兼容性) — Task 13 验证
- §5.3 (/诊断 渲染不动) — 全 plan 不改渲染
- §5.4 (高价值消息保护不动) — 全 plan 不动算法
- §6 实施步骤 — Task 1-14

**2. Placeholder scan:** 无 TBD/TODO/类似 implement later 字样. ✅

**3. Type consistency:**
- `diagnostics: dict[str, Any] | None` 一致
- `compaction_strategy: str` 一致
- `compaction_tail_turns_kept: int` 一致
- `compaction_split_turn_applied: bool` 一致
- `compaction_preserved_recent_budget: int` 一致
- `compaction_tail_token_count: int` 一致
- `compaction_tail_start_index: int` 一致
- `_strategy_label(tail_turns_kept: int, split_applied: bool, middle_present: bool) -> str` 一致 (3 形参, 无 fell_back)
- `select_tail_start_index` 签名在 Task 3 + 6 完整 (最后含 diagnostics)
- `split_head_tail_turns` 签名在 Task 6 加 diagnostics
- `try_reactive_compact` 签名在 Task 12 加 diagnostics
- `compress_messages` 已在 (Task 8 不改签名, 只在调用处加 diagnostics kwarg)

✅ 全部一致.

---

**Plan complete. Estimated 14 tasks, ~14 commits, ~1 sprint 内可完成.**
