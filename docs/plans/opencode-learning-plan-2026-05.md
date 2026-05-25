# OpenCode 对标学习规划（Butler v4）

> **状态**：P0–P1 已落地（2026-05-25，零依赖）  
> **源码**：[reference/opencode](../../reference/opencode)（gitignore，本地对照）  
> **原则**：只借鉴设计，不引入 Effect-TS / Drizzle / AI SDK / MCP SDK  
> **主学习线**：仍优先 [cc-butler-gap-analysis-2026-05.md](cc-butler-gap-analysis-2026-05.md)  
> **索引**：[README.md](README.md)

---

## 1. 边界

| 做 | 不做 |
|----|------|
| 压缩模板、工具输出 prune、doom loop、last-match 权限 | MCP Host、npm 插件、HTTP 多客户端网关 |
| cache token 计入 overflow、`/诊断` 展示 | 完整事件溯源 + Effect projector |
| 委派权限继承、`child_session_key` / `task_id` | 确认后自动续跑 workflow |
| `read_file` 后 AGENTS.md walk-up | SQLite message/part 全量模型（P2 按需） |

---

## 2. OpenCode 核心文件索引

| 能力 | 路径 |
|------|------|
| 主循环 | `packages/opencode/src/session/prompt.ts` |
| 流处理 / doom loop | `packages/opencode/src/session/processor.ts` |
| 压缩 + prune | `packages/opencode/src/session/compaction.ts` |
| Overflow | `packages/opencode/src/session/overflow.ts` |
| 权限求值 | `packages/core/src/permission.ts` |
| 子代理权限 | `packages/opencode/src/agent/subagent-permissions.ts` |
| 会话互斥 | `packages/opencode/src/session/run-state.ts` |

---

## 3. Butler 映射（已落地）

| 项 | 模块 | 配置 / 命令 |
|----|------|-------------|
| P0 压缩模板 | `butler/core/compaction_prompt.py` | `BUTLER_COMPACTION_USE_OPENCODE_TEMPLATE` |
| P0 工具 prune | `butler/core/tool_output_prune.py` | `BUTLER_TOOL_PRUNE_BACKWARD_*` |
| P0 last-match 权限 | `butler/permissions.py` | `permissions.yaml` 后写覆盖前写 |
| P0 doom loop | `butler/tool_guardrails.py` | `BUTLER_DOOM_LOOP_THRESHOLD`（0=关） |
| P1 cache overflow | `butler/core/context_budget.py` | `/诊断` 上下文行 |
| P1 子代理权限 | `butler/delegate_subagent_permissions.py` | `delegate_subagent` in permissions.yaml |
| P1 task 恢复 | `butler/runtime/task_store.py`、`report.py` | `/任务`、`/详细`；`child_session_key` |
| P1 instruction walk-up | `butler/core/instruction_walkup.py` | `BUTLER_INSTRUCTION_WALKUP_*` |

---

## 4. P2 暂缓

- 压缩 task part 入队（改 loop 结构）
- SQLite session/message/part 规范化
- post-commit 副作用队列（记忆 + outbound）

---

## 5. 决策记录

| # | 结论 |
|---|------|
| D1 | 不嵌入 OpenCode 运行时 |
| D2 | 权限 last-match 为 **行为变更**，YAML 靠后规则优先 |
| D3 | doom loop 执行前拦截，非 OpenCode UI Deferred |
| D4 | `child_session_key` 格式 `{session}::delegate::{task_id}` |

---

*对照完成：2026-05-25*
