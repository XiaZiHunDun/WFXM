# P1-3.1 Turn-Based Compaction `/诊断` 可见策略

> **设计日期**：2026-06-04
> **对应审计项**：`docs/plans/active/opencode-actionable-optimization-checklist-2026-05.md` §3.1
> **状态**：设计批准，待实施
> **作者**：Claude (brainstorming skill)

---

## 1. 背景与目标

### 1.1 OpenCode §3.1 验收标准
1. 长工具链会话中，最近 2 个 user turn 在预算内优先保留
2. 当最新 turn 过大时，允许从 turn 中部开始保留后半段，而不是整体丢弃
3. **`/诊断` 能看见本轮压缩采用了何种尾选择策略** ← 本次收口项
4. 不能把 `delegate_task` / `patch` 这类高价值消息误裁掉

### 1.2 现状盘点 (2026-06-04 调研)
- ✅ **§3.1.1 + 3.1.2 + 3.1.4 已实现** — `butler/core/turn_compaction.py` (253 行) + `butler/core/turn_token_budget.py` (147 行) + 7 单测 + 已接入 `context_compressor.py:265-298` 与 `reactive_compact.py:50-75`，默认开启。
- ❌ **§3.1.3 未达** — 现有 `diagnostics["compaction_turn_fallback"]` 只在 fallback 时写入（rarely-seen），缺一个 always-on 的策略指标。

### 1.3 本次收口范围
**只解决 §3.1.3**。不动算法、不动 env toggle、不动 `/诊断` 渲染代码（新增字段会自动出现）。

---

## 2. 设计决策

### 2.1 写入点选择
**选 A**：`select_tail_start_index()` 加可选 `diagnostics` 形参，计算中写入。理由：
- 信息最准确（在算法最内层记录）
- 函数签名薄改（仅新增 kw-only 形参，默认 `None`）
- 现有 5 个调用方不传 `diagnostics` → 0 行为变化
- 现有 7 个测试不需要改

### 2.2 字段集
| 字段 | 类型 | 含义 |
|------|------|------|
| `compaction_strategy` | `str` | 主策略标签（见 §2.3） |
| `compaction_tail_turns_kept` | `int` | 实际保留的 turn 数 |
| `compaction_split_turn_applied` | `bool` | mid-turn split 是否触发 |
| `compaction_preserved_recent_budget` | `int` | 本次预算 token 数 |
| `compaction_tail_token_count` | `int` | 实际尾 token 数 |
| `compaction_tail_start_index` | `int \| None` | tail 在 body 中起点（`None`=no_op） |

### 2.3 策略标签生成
```python
def _strategy_label(
    tail_turns_kept: int,
    split_applied: bool,
    middle_present: bool,
) -> str:
    if not middle_present:
        return "no_op"
    base = f"turns:{tail_turns_kept}"
    return f"{base}+split" if split_applied else base
```

`_strategy_label` 不处理 `fell_back`（它不知道是否走了 fallback），由调用方在 try/except 里直接 `diagnostics["compaction_strategy"] = "legacy_split"`。

枚举：
- `turns:1` / `turns:2` / `turns:3` — turn-based 无 split
- `turns:1+split` / `turns:2+split` — turn-based + mid-turn split
- `legacy_split` — turn_compaction 抛异常时由调用方（`compress_messages` / `try_reactive_compact`）直接写入
- `no_op` — 无 middle（消息总数 ≤ head + min_tail）

### 2.4 Fallback 标记
- 现有 `diagnostics["compaction_turn_fallback"] = "legacy_split"` 保留
- 本次新增 `compaction_strategy = "legacy_split"` 在同场景下与之并存
- 两个字段职责正交：fallback 表示"用了旧路径"，strategy 表示"完整策略名"

---

## 3. 改动面

### 3.1 `butler/core/turn_compaction.py`
**`select_tail_start_index` 加 1 个 kw-only 形参：**
```python
def select_tail_start_index(
    rest: list[dict],
    *,
    max_context_tokens: int,
    max_output_tokens: int | None = None,
    tail_turns: int | None = None,
    split_turn: bool | None = None,
    estimate_fn: Callable[[list[dict]], int] | None = None,
    diagnostics: dict[str, Any] | None = None,  # NEW
) -> int:
```

实现：
- 函数末尾（return 之前）根据本次执行的真实状态写入 6 字段
- 新增私有 `_strategy_label()` helper

**`split_head_tail_turns` 透传 diagnostics：**
```python
tail_start = select_tail_start_index(
    body,
    max_context_tokens=max_context_tokens,
    max_output_tokens=max_output_tokens,
    estimate_fn=estimate_fn,
    diagnostics=diagnostics,  # NEW
)
```

### 3.2 `butler/core/context_compressor.py`
`compress_messages` 在调用 `split_head_tail_turns` 时把 `diagnostics` 透传：
```python
if turn_compaction_enabled():
    system, middle, head_tail = split_head_tail_turns(
        pruned,
        max_context_tokens=max_tokens,
        max_output_tokens=max_output_tokens,
        head_count=head_count,
        min_tail_messages=min_tail_messages,
        estimate_fn=_estimate_tokens,
        diagnostics=diagnostics,  # NEW
    )
```
`split_head_tail_turns` 签名同步加 `diagnostics: dict | None = None` kw-only 形参并透传给 `select_tail_start_index`。

### 3.3 `butler/core/reactive_compact.py`
`try_reactive_compact` 的 turn-mode 分支也写 strategy 字段：
- 入参加 `diagnostics: dict | None = None`
- 当 `use_turn_tail=True` 且成功压缩时，写入：
  - `compaction_strategy: "turns:N"` （N=保留的 turn 数，与主路径同名同义）
  - `reactive_compact_strategy: "turns:N"` （reactive 专属字段，便于区分 reactive vs 主压缩）
- 不动 reactive 路径的 `reactive_compact_applied` / `reactive_compact_reason`
- 异常时（line 73 返 `("error", ...)`）不写 `compaction_strategy`，由上层 `apply_reactive_compact_to_messages` 决定是否需要 "legacy" 标记（本次不动）

### 3.4 `tests/test_turn_compaction.py`
新增 6 个测试（见 §4.2）。

---

## 4. 测试计划

### 4.1 既有测试 (7 个, 不动)
全部通过 `select_tail_start_index(rest, ..., diagnostics=None)` 验证算法不变。

### 4.2 新增测试 (6 个)

| 测试名 | 验证目标 |
|--------|---------|
| `test_diagnostics_strategy_turns_2` | 8 turn 场景 → `compaction_strategy = "turns:2"`、`tail_turns_kept = 2`、`split_turn_applied = False` |
| `test_diagnostics_strategy_turns_2_split` | 单 turn 超大 → `"turns:2+split"` + `split_turn_applied = True` + `tail_start_index > 0` |
| `test_diagnostics_no_op_when_few_messages` | 4 turn ≤ head + min_tail → `"no_op"` + `tail_start_index = 0` |
| `test_diagnostics_via_compress_messages` | 端到端：调 `compress_messages(messages, diagnostics={})` 验证 dict 含 6 字段 |
| `test_diagnostics_no_op_when_none` | `diagnostics=None` 时仍正常返回 0/keep_start（不抛错） |
| `test_diagnostics_legacy_fallback_on_exception` | mock turn_compaction 抛异常 → `compaction_turn_fallback = "legacy_split"` 仍触发 |

### 4.3 验收标准
- `pytest tests/test_turn_compaction.py -v` 全过
- 6 个新测试 + 7 个旧测试 = 13 个全过
- `pytest tests/test_context_compressor.py tests/test_reactive_compact.py` 现有测试无回归

---

## 5. 风险与兼容性

### 5.1 签名兼容性
- `select_tail_start_index` 新增 `diagnostics=None` kw-only 形参 → 所有现有调用继续工作
- `split_head_tail_turns` 同步加 → 现有 2 个调用方（`context_compressor.py` + 内部递归）继续工作
- 旧测试断言返回值不受影响

### 5.2 行为兼容性
- 现有 7 个 turn_compaction 测试断言 `start` 索引，**不检查 diagnostics** → 全过
- 现有 compress_messages 测试断言压缩结果 dict 内容（`compaction_remote`、`compaction_turn_fallback`），**不检查新增 6 字段** → 全过
- `diagnostics=None` 路径（5 个调用方）→ 算法照跑，dict 写入被 short-circuit

### 5.3 `/诊断` 渲染
**不需改**。`/诊断` 输出读取 `diagnostics` dict 现有键（`compaction_remote` / `compaction_turn_fallback` 等），新 6 键自然出现在输出中。如有格式化需求，**后续**单独 sprint 收口。

### 5.4 高价值消息保护
本次**不动**。理由：turn-based tail 总是保留最近 2 turn，`delegate_task` / `patch` 等高价值消息作为最近 user turn 的内容自然在 tail 内，不会被裁。OpenCode §3.1.4 风险已通过"tail 永远保留"机制规避。

---

## 6. 实施步骤 (TDD)

1. **RED** — 写 6 个新测试
2. **GREEN** — 改 3 个文件：
   - `turn_compaction.py`: `_strategy_label()` + `select_tail_start_index` 写入 + `split_head_tail_turns` 透传
   - `context_compressor.py`: `compress_messages` 透传
   - `reactive_compact.py`: `try_reactive_compact` turn-mode 写入
3. **VERIFY** — 13 个测试全过 + 现有 1242 passed 无回归
4. **COMMIT + checklist** — 改 opencode §3.1 标记为 ✅

---

## 7. 验收

- [ ] `pytest tests/test_turn_compaction.py` 13/13 过
- [ ] `pytest tests/test_context_compressor.py tests/test_reactive_compact.py` 无回归
- [ ] `diagnostics` 6 字段在 `compress_messages(messages, diagnostics={})` 输出中可见
- [ ] `/诊断` 实际渲染含 `compaction_strategy: turns:2+split` 等策略标签（手动验证）
- [ ] opencode §3.1 标记为 ✅

---

## 8. 一句话结论

本次只动"诊断可见性"，不动算法、不动 toggle、不动渲染。约 30 行代码 + 6 测试 + 1 audit 勾选，可在 1 个 sprint 内完成。
