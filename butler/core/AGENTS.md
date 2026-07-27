# Butler Core — L3 认知推理环

> **层级**：L3 认知推理环  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7 Butler Core

## 目录结构

```
butler/core/
├── __init__.py                    # 导出子包结构
├── agent_loop/                    # Agent Loop（主循环）
│   ├── __init__.py
│   ├── loop.py                    # AgentLoop 主类
│   └── phases.py                  # 阶段函数（init/call_llm/dispatch/finalize）
├── agent_loop.py                  # shim（向后兼容，已弃用）
├── agent_loop_phases.py           # shim（向后兼容，已弃用）
├── context/                       # 上下文管线
├── compaction/                    # 压缩模块
├── tool/                          # 工具批次处理
├── session/                       # 会话状态
├── llm/                           # LLM 重试
├── loop/                          # Loop 类型与中间件
└── （其他独立模块）
```

## 子包说明

| 子包 | 职责 | 主要模块 |
|------|------|----------|
| `agent_loop/` | Agent 主循环 | `loop.py`（AgentLoop）、`phases.py`（阶段函数） |
| `context/` | 上下文管线 | context_pipeline, context_compressor, context_budget |
| `compaction/` | 对话压缩 | turn_compaction, turn_summarizer, preemptive_compact |
| `tool/` | 工具批次处理 | tool_batch, tool_dispatch, tool_result_storage |
| `session/` | 会话状态 | session_transcript, conversation_state, session_todos |
| `llm/` | LLM 重试 | llm_retry, llm_retry_errors, llm_retry_ops |
| `loop/` | Loop 类型 | loop_types, loop_middleware, goal_loop, parallel_tools |

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `agent_loop/loop.py` | AgentLoop 主类，核心对话引擎 | ~560 |
| `context_pipeline.py` | 上下文管线（压缩、hygiene、剪枝） | ~12870 |
| `context_compressor.py` | 上下文压缩核心逻辑 | ~13190 |
| `tool_result_storage.py` | 工具结果落盘与预算管理 | ~19250 |
| `session_transcript.py` | 会话 transcript 管理 | ~16930 |
| `conversation_state.py` | 会话状态管理 | ~26240 |
| `turn_summarizer.py` | 轮次摘要生成 | ~11070 |
| `turn_compaction.py` | 轮次压缩 | ~10960 |
| `llm_retry.py` | LLM 调用重试逻辑 | ~2900 |
| `tool_batch.py` | 工具批次处理 | ~6580 |
| `tool_dispatch.py` | 工具分发 | ~8530 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| `AgentLoop` | `agent_loop/loop.py` | 主循环类，处理对话轮次 |
| `ContextPipeline` | `context_pipeline.py` | 上下文处理管线 |
| `process_tool_calls` | `tool_batch.py` | 处理工具调用批次 |
| `call_llm_with_retry` | `llm_retry.py` | LLM 调用带重试 |
| `LoopConfig` / `LoopResult` | `loop_types.py` | Loop 配置与结果类型 |

## 数据流

```
用户消息 → AgentLoop.run_turn()
              │
              ├→ _phase_init()         # 初始化
              ├→ _phase_resolve_user_text()  # 解析用户文本
              ├→ _phase_enrich_user_text()  # 增强用户文本
              ├→ maybe_compact_turn_safe()  # 压缩检查
              ├→ _phase_call_llm()     # 调用 LLM
              ├→ _phase_dispatch_tools() # 分发工具调用
              └→ _phase_finalize()     # 收尾
```

## 注意事项

1. **向后兼容**：`agent_loop.py` 和 `agent_loop_phases.py` 是 shim 文件，已弃用，新代码应从 `agent_loop/` 包导入
2. **子包导入**：`context/`、`compaction/`、`tool/`、`session/`、`llm/`、`loop/` 是组织性包，实际代码仍在 `butler/core/` 根目录
3. **大文件**：多个模块超过 10000 行，后续可考虑进一步拆分

## 相关目录

- L2 编排：[`../orchestrator/`](../orchestrator/)
- L4 工具：[`../tools/`](../tools/)
- L5 记忆：[`../memory/`](../memory/)
