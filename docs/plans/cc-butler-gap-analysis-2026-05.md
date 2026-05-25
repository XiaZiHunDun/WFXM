# Claude Code ↔ Butler v4 差距分析

> **状态**：活跃参考（2026-05-22）  
> **对照源**：`reference/claude-code-bak`（`claude-code/`、`claude-code-source-code/`、`claude-code-sourcemap/restored-src/`）  
> **产品边界**：[`project-layer-wechat-plan.md`](../architecture/project-layer-wechat-plan.md)、[`post-consolidation-roadmap-2026-05.md`](post-consolidation-roadmap-2026-05.md)  
> **设计基线**：[`design.md`](../design/design.md) §9.1–9.2

---

## 1. 三份 Claude Code 源码说明

| 目录 | 用途 |
|------|------|
| `claude-code/` | 裸 `src/`（约 1884 个 TS 文件） |
| `claude-code-source-code/` | 同上 + 架构 README、`docs/` 深度报告 |
| `claude-code-sourcemap/restored-src/` | 从 v2.1.88 sourcemap 还原，最完整（含 vendor） |

三份 `src/` 内容一致；**sourcemap 版**便于查 `query.ts`、`microCompact.ts` 等。约 108 个 `feature()` 门控模块在 bundle 里被 DCE，源码树里可能缺 `reactiveCompact` 等——**对比时以已还原文件为准**。

---

## 2. 架构对照（Butler vs Claude Code）

| 维度 | Claude Code | Butler v4 | 差距 |
|------|-------------|-----------|------|
| Agent 循环 | `query.ts` 状态机 + 明确 transition 原因 | `agent_loop.py` 模块化 while | **中** |
| 上下文压缩 | 三层：micro → auto → session memory | 单层 LLM 摘要 + `prune_tool_outputs` | **大**（见 §4 核验） |
| 工具结果 | 超大结果落盘 + 模型按需 Read | 截断/剪枝到 ~800 字符 | **大** |
| 工具执行 | 流式并行 `StreamingToolExecutor` | 批结束后 `parallel_tools` | **中** |
| 运行中输入 | 优先级队列 now/next/later + QueryGuard | `/steer` 注入 tool 结果 | **中** |
| 读后再改 | readFileState + mtime | `design.md` 规划，**未实现** | **大** |
| 权限 | 规则引擎 + LLM classifier | plan mode + owner gate + 工具开关 | **中** |
| 记忆 | CLAUDE.md + memdir | 分层 memory + post_session | **Butler 更强**（多项目） |
| 子 Agent | `runAgent()` + cache-safe fork | TaskOrchestrator + `delegate_task` | 各有优势 |
| 会话持久化 | JSONL sessionStorage | Gateway session + `.butler/` | **中** |
| MCP | 一等公民 | 无内置 MCP host | **大**（产品定位不同） |
| 入口场景 | IDE/本地 REPL | 微信远程 + 多项目 | **刻意不同** |

`design.md` §9.2 已列出部分借鉴项；下文按源码证据 + Butler 现状重新排序。

---

## 3. Butler 现状核验（代码，2026-05-22）

与报告结论的对照修正，避免重复造轮子：

| 报告表述 | 实际代码 | 说明 |
|----------|----------|------|
| 「每轮常走 LLM 摘要」 | `context_pipeline.prepare_messages_for_api`：`prune` → `compress_context` | `compress_messages` **仅在** `estimated > threshold` 且消息数 ≥ 12 时调辅助模型摘要；否则 no-op |
| 「无 micro 先行」 | `context_compressor._prune_tool_outputs` | **已有** micro 风格剪枝，但是 **统一 800 字符**，未按工具名分级 |
| 「无 post-compact 重注入」 | `post_compact_cleanup.py` | 仅清理 hygiene 诊断标记；**未**重注入 MEMORY / Skill / 活跃任务锚点 |
| 「patch 无 read state」 | `design.md` §9.2 | 与代码一致：无 `ReadStateStore` |
| 「transition 不可观测」 | `loop_types.LoopResult` | 有 `LoopStatus`，**无** `transition_reason`；gateway 有 completion/hook 遥测，无 loop transition 枚举 |
| 「Prompt 缓存已实现」 | 需单独审计 delegate/orchestrator | 报告写「已在架构中」——委派仍全量新 loop，**cache-safe fork 仍待做**（P2） |

---

## 4. 高优先级（P0，1–2 周）

微信长会话稳定性、降 token 费。

### 4.1 三层上下文压缩（micro → auto → full） ✅ 部分落地（2026-05-22）

- **micro**：`tool_prune_policy.py` 按工具分级 + 旧结果清空；`post_compact_cleanup.py` 压缩后重注入 MEMORY/任务锚点  
- **auto**：原有 `compress_messages` 阈值门控不变  
- 测试：`tests/test_tool_prune_policy.py`、`test_context_pipeline` post-compact 用例

**CC**：`microCompact.ts` 按工具类型清空旧 read/bash/grep；`autoCompact.ts` 达阈值 LLM 摘要；`postCompactCleanup.ts` 补注入附件。

**Butler 缺口**：

1. **每轮固定顺序**：`prune_tool_outputs` → **仅当** token > 阈值才 `compress_context`（顺序已有，需避免 hygiene/多处重复 prune 行为不一致）。
2. **按工具名分级剪枝**：read/search/terminal 可清；write/patch/delegate 报告保留更长摘要或指针。
3. **压缩后重注入**：扩展 `run_post_compact_cleanup`：当前项目 `MEMORY.md` 摘要、活跃 Skill、任务锚点（对齐 CC postCompactCleanup 语义）。

**参考**：`reference/.../services/compact/microCompact.ts`、`autoCompact.ts`  
**改动**：`butler/core/context_pipeline.py`、`context_compressor.py`、`post_compact_cleanup.py`

### 4.2 大工具结果落盘（tool result spill） ✅ 已落地（2026-05-22）

**CC**：`toolResultStorage.ts` → `tool-results/`，上下文留 `<persisted-output>` 指针。

**Butler**：`butler/core/tool_result_storage.py` + `tool_batch` 写入消息前 spill；`micro` 剪枝跳过已落盘块。

- 路径：`~/.butler/sessions/<session_key>/tool-results/<tool_use_id>.txt`
- 环境变量：`BUTLER_TOOL_RESULT_SPILL`、`BUTLER_TOOL_RESULT_SPILL_MIN_CHARS`（默认 8192）、`BUTLER_TOOL_RESULT_SPILL_PREVIEW_CHARS`
- 测试：`tests/test_tool_result_storage.py`

### 4.3 读后再改 + mtime（edit safety） ✅ 已落地（2026-05-22）

**Butler**：`butler/core/read_state.py`；`read_file` 记录 mtime/哈希；`patch`/`write_file`（已有文件）返回 `READ_STATE_REQUIRED` / `READ_STATE_STALE`；`patch` 支持弯引号模糊匹配；`/新对话` 重置。

- 环境变量：`BUTLER_READ_BEFORE_EDIT`（默认 `1`）
- 测试：`tests/test_read_state.py`（pytest 默认关闭以免破坏旧用例）

### 4.4 循环 transition 原因 + 可观测性 ✅ 已落地（2026-05-22）

- `LoopTransitionReason` + `LoopResult.transition_reason`；`/诊断` 显示 **上轮循环结束**
- 测试：`tests/test_loop_transition.py`

**CC**：`query.ts` — `reactive_compact_retry`、`token_budget_continuation`、`stop_hook_blocking` 等。

**Butler**：扩展 `LoopResult.transition_reason`，写入 gateway telemetry 与 `/诊断`（或 `/health`）。

**改动**：`loop_types.py`、`agent_loop.py`、`gateway/completion_telemetry.py`（或统一 loop telemetry 模块）

---

## 5. 中优先级（P1）

| # | 项 | 状态 |
|---|-----|------|
| 5 | 流式工具执行 | **P2**（需改 transport 流式增量 dispatch） |
| 6 | 消息优先级队列 | ✅ `butler/gateway/message_queue.py` |
| 7 | Token budget 续跑 | ✅ `butler/core/turn_token_budget.py` |
| 8 | Stop 钩子 block | ✅ `StopHookResult.blocked` + `stop_hook_blocked` 诊断 |
| 9 | Cache-safe delegate | **P2** |

---

## 6. 低优先级 / 按需

| 项 | 说明 |
|----|------|
| MCP 一等公民 | 薄客户端调用外部 MCP 即可，不必 IDE 内嵌 |
| IDE/LSP/打开文件列表 | 文档已明确不控 IDE |
| Tasks V2 + Ink UI | 轻量 todo + 微信卡片代替 |
| Swarm/teammate | 现有 TaskOrchestrator DAG 足够 |
| Worktree 模式 | 微信远程价值低 |
| GrowthBook flags | `env` + `ButlerSettings` 简化版 |

---

## 7. Butler 已做对、不必照搬

- 多项目 + Lead + `project.yaml` 工具白名单  
- post_session 双通道（memory + skills）  
- 微信：媒体 STT/VLM、owner gate、session LRU、`outbound_bridge` 进度  
- 语料门禁 `corpus-test.sh`  
- Shell hooks 事件名兼容（`hooks/runner.py`）  
- `parallel_tools.py` 路径冲突检测（差在**流式触发时机**）

---

## 8. 落地路线图（与仓库规划对齐）

| 阶段 | 内容 | 收益 |
|------|------|------|
| **P0** | 工具分级剪枝 + post-compact 重注入；tool result spill；`transition_reason` | 长会话稳定、降 token、可排障 |
| **P1** | read-before-edit + mtime；Stop block；消息优先级队列 | 少改错文件、主公遥控 |
| **P2** | 流式工具；token budget 续跑；cache-safe delegate | 延迟与成本 |
| **不做** | IDE/MCP 全家桶、Swarm UI | 符合微信管家边界 |

**合并到运营规划**：轨道 D 按需项可与 [`post-consolidation-roadmap-2026-05.md`](post-consolidation-roadmap-2026-05.md) 并行；发版验收继续用 [`wechat-daily-smoke-checklist.md`](../guides/wechat-daily-smoke-checklist.md) **H1–H10** + [`CONTRIBUTING.md`](../../CONTRIBUTING.md) Butler 线束节。

---

## 9. 小结

Claude Code 的核心优势在 **上下文经济学**（micro 剪枝 + 落盘 + 分层 compact）、**编辑安全**（read state）、**运行时控制**（队列 steer、transition 可观测、流式工具）。Butler 在 **多项目记忆、微信网关、委派编排** 上已超 CC 的产品适配。

**P0 四项（2026-05-22）均已落地**：落盘、分级 micro + post-compact 锚点、`transition_reason`、read-before-edit + mtime。

**P1（2026-05-22 已落地）**：入站消息队列（`message_queue.py`）、Stop 钩子 `block`、turn token 预算（`+500k` / `/budget` / 「本轮尽量做完」）。

**P2 候选**：流式工具执行、cache-safe delegate、消息队列出站 follow-up（bridge 主动推送 drain 回复）。

其余按微信远程场景取舍。

---

## 10. 建议开工顺序（实现）

| 顺序 | 项 | 理由 |
|------|-----|------|
| 1 | ~~**tool_result_storage**~~ | ✅ |
| 2 | ~~**工具分级剪枝 + post_compact 重注入**~~ | ✅ |
| 3 | ~~**transition_reason**~~ | ✅ |
| 4 | ~~**read_state + mtime**~~ | ✅ |
| 4 | **read_state + mtime** | 触及 patch/write 全路径，需 fuzz/回归 |
