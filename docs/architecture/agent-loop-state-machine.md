# Agent Loop 状态机（Butler v4）

> **状态**：2026-06 · AP-7  
> **代码 SSOT**：[`butler/core/loop_types.py`](../../butler/core/loop_types.py) · [`butler/core/agent_loop.py`](../../butler/core/agent_loop.py)  
> **关联**：Gateway 锁定阶段 [`locked_phases.py`](../../butler/gateway/locked_phases.py) · 门控 [`permission-gate-stack.md`](permission-gate-stack.md)

## 1. 定位

Butler **不** 使用 LangGraph；主会话为 **ReAct while-loop**，终止原因由 `LoopTransitionReason` 枚举表达。Workflow DAG 由 `task_orchestrator` 单独建模。

本文件是 **规范层状态表**，用于单测覆盖与排障，不是第三方 StateGraph 源码。

## 2. LoopStatus（对外终态）

| 值 | 含义 |
|----|------|
| `running` | 迭代中（通常不持久化为终态） |
| `completed` | 正常完成一轮 |
| `tool_limit` | 达到 `max_iterations` |
| `error` | LLM/内部错误 |
| `interrupted` | 用户 `/停止` 或 session interrupt |
| `waiting_confirmation` | 两阶段确认 / doom-loop ask |
| `stuck` | 无进展检测 |

## 3. LoopTransitionReason（终止/继续原因）

| 枚举值 | 典型触发 | Gateway `/诊断` |
|--------|----------|-----------------|
| `turn_completed` | 模型返回纯文本、无 tool_calls | 是 |
| `tool_batch_continue` | 工具批执行后继续迭代 | 是 |
| `should_continue_false` | 策略判定不应继续 | 是 |
| `truncation_continue` | 输出截断后继续 | 是 |
| `tool_limit` | 迭代上限 | 是 |
| `interrupted` | interrupt 标志 | 是 |
| `llm_error` | provider/transport 失败 | 是 |
| `reactive_compact_retry` | 413 压缩后重试 | 是 |
| `compaction_turn` | 专用压缩轮 | 是 |
| `stop_hook_blocked` | stop hook 拒绝结束 | 是 |
| `token_budget_continue` | `+500k` 预算续跑 | 是 |
| `prompt_too_long` | 上下文过长 | 是 |
| `max_output_recovery` | max_tokens 恢复路径 | 是 |
| `safety_finish` | 安全结束启发式 | 是 |
| `waiting_confirmation` | 待 Owner 确认 | 是 |
| `stuck` | stuck 检测 | 是 |
| `unknown` | 未分类 | 是 |

单测覆盖入口：[`tests/test_loop_transition_coverage.py`](../../tests/test_loop_transition_coverage.py) · 行为 [`tests/test_loop_transition.py`](../../tests/test_loop_transition.py)

## 4. 与 Gateway locked_phases 关系

```text
入站 locked_phases
  → recall_banner / memory_prefetch
  → use_session_read_recall_gate (可选)
  → AgentLoop.run
  → transition_reason → completion 遥测 / LangFuse (opt-in)
```

压缩、interrupt、human_gate **不**改变 Loop 枚举定义；它们改变 **输入消息** 或 **是否调用** `AgentLoop.run`。

## 5. Workflow DAG（并行轨道）

| 组件 | 状态 |
|------|------|
| `task_orchestrator.execute_graph` | 拓扑调度 + 并行 `asyncio.to_thread` |
| `human_gate.check_workflow_step_approval` | 步骤级 T6 门控 |
| `workflow_step_runner` | retry / rescue 边 |

Checkpoint 文件默认 **只写不读**；见 `permission-gate-stack.md` §7。

## 6. 排障顺序（与 AP-6 一致）

1. `runtime_metrics` / structured `llm_api_call` / `retrieval_degraded`
2. `LoopTransitionReason` on `/诊断`
3. `session_transcript.jsonl` 工具行（语义层）
