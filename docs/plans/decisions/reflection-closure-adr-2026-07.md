# ADR：Reflection 写回闭环（Reflection Closure）

> **状态**：已采纳（2026-06-30）  
> **边界**：`record_reflect_step` / Reflexion → `reflexion.jsonl` → 下轮 `memory_prefetch` 注入  
> **关联**：五报告 H · [`reflection_closure.py`](../../butler/core/reflection_closure.py)

## 背景

此前 Reflection 分散在 transcript `reflect_step`、opt-in `BUTLER_REFLEXION_EPHEMERAL`、默认关的 `BUTLER_REFLEXION_WRITE_EXPERIENCE`，缺少统一写回与下轮注入。

## 决策

1. **模块**：`butler/core/reflection_closure.py`
2. **写回**：`BUTLER_REFLECTION_CLOSURE=1`（默认开）时，`record_reflect_step` 经 `maybe_persist_reflect_closure` 可追加 `reflexion.jsonl`
3. **写入门控**：`BUTLER_REFLECTION_CLOSURE_WRITE=1` 或 `BUTLER_REFLEXION_WRITE_EXPERIENCE=1`（默认均关 persist，避免无意写盘）
4. **注入**：`BUTLER_REFLECTION_CLOSURE_INJECT=1`（默认开）时，`memory_prefetch._decorate_prefetch_for_turn` 前置 `## Reflection（近期）` 横幅
5. **工具失败**：`reflexion_ephemeral.maybe_apply_reflexion` 同时走 legacy write + closure persist

## 非目标

- TradingAgents 式独立 Reflector LLM 节点
- 默认开启 `BUTLER_REFLEXION_EPHEMERAL`（仍 opt-in）

## 验收

- `tests/core/test_reflection_closure.py` 绿
- `record_reflect_step` 写盘后下轮 prefetch 可见 `reflection_closure_injected`
