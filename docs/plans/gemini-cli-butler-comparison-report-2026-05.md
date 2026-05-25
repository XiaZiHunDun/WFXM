# Gemini CLI ↔ Butler v4 对照分析报告

> **状态**：分析完成（2026-05-25）；**Sprint A 子集已落地**（见 [`../guides/sprint-roadmap-2026-05.md`](../guides/sprint-roadmap-2026-05.md)）；其余 defer  
> **对照源**：`reference/gemini-cli`（Google [gemini-cli](https://github.com/google-gemini/gemini-cli)，本地只读）  
> **Butler 基线**：[`v4-architecture.md`](../architecture/v4-architecture.md)、[`cc-butler-gap-analysis-2026-05.md`](cc-butler-gap-analysis-2026-05.md)  
> **原则**：只借鉴设计，映射到现有 `butler/core`、`butler/gateway`、`butler/permissions`；不引入 Gemini CLI 运行时或 npm 生态。

---

## 1. 文档目的

对比 **Gemini CLI** 与 **Butler v4** 的 Agent Loop、上下文经济学、工具调度、权限与循环检测，列出 Butler **已对齐**、**可提炼优化** 与 **不宜照搬** 项，并给出可执行的落地顺序。

---

## 2. 架构对照

| 维度 | Gemini CLI | Butler v4 |
|------|------------|-----------|
| 主循环 | `packages/core/src/core/client.ts`（`GeminiClient.processTurn`）+ `turn.ts` 事件流 | `butler/core/agent_loop.py` |
| LLM 层 | `geminiChat.ts` + `contentGenerator.ts` | `butler/transport/llm_client.py` + 多 Provider |
| 工具调度 | `scheduler/scheduler.ts`（状态机 + 并行波次） | `tool_batch.py` + `parallel_tools.py` |
| 上下文 | `ChatCompressionService` + `ToolOutputMaskingService` + 可选 `ContextManager` 图管线 | `context_pipeline.py` + `context_compressor.py` + `tool_output_prune.py` |
| 权限 | `policy/policy-engine.ts` + `ApprovalMode` + Sandbox | `permissions.py` + workflow / plan mode |
| 记忆 | 分层 `GEMINI.md` + `memoryDiscovery.ts` | 多项目 `MEMORY.md` + orchestrator 注入 |
| 入口 | 终端 REPL / IDE Companion / MCP 一等公民 | 微信 Gateway + CLI |
| 子 Agent | `agent/agent-session.ts` + AGENT 工具 | `delegate_task` + `task_orchestrator.py` |

```text
Gemini CLI (core)                    Butler v4
─────────────────                    ─────────
GeminiClient                         agent_loop
  ├─ ChatCompressionService            ├─ context_pipeline
  ├─ ToolOutputMaskingService          ├─ tool_output_prune / tool_result_storage
  ├─ Scheduler (policy→confirm→exec)   ├─ tool_batch + parallel_tools
  ├─ PolicyEngine                      ├─ permissions.py
  └─ LoopDetectionService              └─ tool_guardrails + tool_loop_detect
```

**源码入口（Gemini，便于 grep）**：

| 场景 | 路径 |
|------|------|
| 主客户端 / 每轮处理 | `packages/core/src/core/client.ts` |
| 压缩 | `packages/core/src/context/chatCompressionService.ts` |
| Tool 输出 mask | `packages/core/src/context/toolOutputMaskingService.ts` |
| 工具调度 | `packages/core/src/scheduler/scheduler.ts` |
| 策略 | `packages/core/src/policy/policy-engine.ts` |
| 循环检测 | `packages/core/src/services/loopDetectionService.ts` |
| History 修复 | `packages/core/src/utils/historyHardening.ts` |
| Next speaker | `packages/core/src/utils/nextSpeakerChecker.ts` |
| 工具 Hook | `packages/core/src/core/coreToolHookTriggers.ts` |

---

## 3. Butler 已对齐或更强的部分

以下能力 Gemini 亦有，但 Butler 已通过 **CC 线束 / Hermes 提炼 / OpenClaw 对标** 落地；**优先做差异增强，勿重写**。

| 能力 | Gemini 参考 | Butler 现状 |
|------|-------------|-------------|
| 分层压缩 | `chatCompressionService.ts` | `context_pipeline` + `tool_prune_policy` + `post_compact_cleanup` |
| 大工具结果外置 | `saveTruncatedToolOutput` | `tool_result_storage.py` spill |
| 读后再改 | edit 工具 + 状态 | `read_state.py` |
| 并行工具 | Scheduler 连续只读波次 | `parallel_tools.py` + `streaming_tools.py` |
| 入站优先级 / steer | `fastAckHelper.ts` 等 | `message_queue.py` + `steer.py` |
| 预检溢出 | `ContextWindowWillOverflow` 事件 | `preemptive_compact.py` + `context_budget.py` |
| 循环 transition 可观测 | `GeminiEventType` | `LoopTransitionReason` |
| 多项目记忆 | `memoryDiscovery.ts` | 更强（项目级 MEMORY + Gateway 会话） |
| 工具循环（启发式） | 阈值 + 内容块 | `tool_guardrails.py` + `tool_loop_detect.py` |
| Cache-safe 委派 | 子 Agent 上下文 | `cache_safe_delegate.py` |
| 会话 transcript | 录制服务 | `session_transcript.py` |

---

## 4. 可提炼优化项（按优先级）

遵循 [`reference-learning-plan-2026-05.md`](reference-learning-plan-2026-05.md)：**零新增 pip/npm 依赖**。

### 4.1 P0 — 微信长会话稳定性 / 降 token（建议 1–2 周）

#### G-P0-1：Tool Output Masking（混合反向 FIFO）

**Gemini**：`ToolOutputMaskingService`（`toolOutputMaskingService.ts`）

- 保护最近约 **50k** tool token（`DEFAULT_TOOL_PROTECTION_THRESHOLD`）及可选「最近一整轮」；
- 更早输出累计可剪枝 token 超 **30k**（`DEFAULT_MIN_PRUNABLE_TOKENS_THRESHOLD`）才批量 mask；
- 落盘到 `tool-outputs/`，上下文留 `tool_output_masked` 类指针。

**Butler**：`backward_prune_tool_outputs`（`tool_output_prune.py`）+ spill（`tool_result_storage.py`）+ micro 剪枝（`tool_prune_policy.py`）— **三条线语义未统一**。

**建议落地**：

- 在 `tool_output_prune.py` 或相邻模块统一：**protect 最近 N token / 最近 user 轮 → 达阈值再清空或写 spill 指针**；
- 与 `tool_result_storage` 共用路径与占位符格式；
- 新增/对齐 `BUTLER_TOOL_MASK_*`（写入 [`config/reference.md`](../config/reference.md)）。

**Butler 映射**：`butler/core/tool_output_prune.py`、`butler/core/tool_result_storage.py`、`butler/core/context_pipeline.py`

---

#### G-P0-2：压缩前 Function Response 预算截断

**Gemini**：`truncateHistoryToBudget`（`chatCompressionService.ts`）

- 压缩摘要前，对旧 `functionResponse` 做**反向 token 预算**（默认 `COMPRESSION_FUNCTION_RESPONSE_TOKEN_BUDGET = 50_000`）；
- 超大结果截断末 30 行并 `saveTruncatedToolOutput` 后再进入 LLM 摘要。

**Butler**：`compress_messages` 阈值门控 + `reactive_compact` / `turn_compaction` replay；**摘要前按 functionResponse 总预算硬截断**不如 Gemini 明确。

**建议落地**：在 `context_compressor.compress_messages` 入口增加可选 `truncate_tool_responses_to_budget()`，复用 spill 目录。

**Butler 映射**：`butler/core/context_compressor.py`

---

#### G-P0-3：压缩失败与「膨胀 token」状态机

**Gemini**：`CompressionStatus` 含 `COMPRESSION_FAILED_INFLATED_TOKEN_COUNT`、`CONTENT_TRUNCATED`；`hasFailedCompressionAttempt` 避免反复失败摘要。

**Butler**：`context_pipeline.consecutive_compact_failures` 已有雏形。

**建议落地**：扩展 `/诊断` 与 `LoopTransitionReason`，区分 **truncated-only / compressed / inflated-fail**。

**Butler 映射**：`butler/core/context_pipeline.py`、`butler/core/loop_types.py`、`butler/ops/` 诊断输出

---

### 4.2 P1 — 可靠性与可观测（建议 2–4 周）

#### G-P1-1：History Hardening（API 不变式 + sentinel）

**Gemini**：`historyHardening.ts` — 角色交替、tool call/response 配对、`thoughtSignature`、空 turn 合并；失败用 sentinel 修补而非抛错。

**Butler**：`message_repair.py`、`tool_pair_repair.py` — 面向 OpenAI/Anthropic 格式，未必覆盖 Gemini 式 part 约束。

**建议**：抽象「不变式检查 + 哨兵注入」，按 `transport` provider 分支。

**Butler 映射**：`butler/core/message_repair.py`、`butler/core/tool_pair_repair.py`、`butler/transport/`

---

#### G-P1-2：LLM 语义循环检测（辅助模型）

**Gemini**：`loopDetectionService.ts` — 启发式（工具重复 5 / 内容 10）+ 30 轮后周期性 **LLM 判定**（区分批量改文件 vs 真死循环），`_recoverFromLoop` 注入纠偏后续跑。

**Butler**：`tool_guardrails` + `tool_loop_detect`（ping_pong / poll / circuit）— **无语义进度判定**。

**建议**（可选 `BUTLER_LLM_LOOP_CHECK=1`）：复用 `auxiliary_client`；仅高迭代或即将 halt 时触发；微信侧简短系统说明。

**Butler 映射**：`butler/tool_guardrails.py`、`butler/core/tool_loop_detect.py`、`butler/transport/auxiliary_client.py`

---

#### G-P1-3：Next Speaker / 截断续跑

**Gemini**：`nextSpeakerChecker.ts` — 末轮若明显未完成（「接下来我将…」、工具未执行），判定 **model 应继续**。

**Butler**：`should_continue` 回调、`todo_continuation`、`turn_token_budget` 分散。

**建议**：无 tool call 完成时增加可选 auxiliary 判定或轻量启发式，映射 `LoopTransitionReason`，与 `TOKEN_BUDGET_CONTINUE` 协调。

**Butler 映射**：`butler/core/agent_loop.py`、`butler/core/todo_continuation.py`

---

#### G-P1-4：Scheduler 语义（批内排序 + `wait_for_previous`）

**Gemini**：`scheduler.ts` — `Validating → Scheduled → Executing`；连续 parallelizable 合并波次；`UPDATE_TOPIC` 批内前置；`wait_for_previous` 控制串行。

**Butler**：`tool_batch` + `parallel_tools`；无统一确认总线（微信交互弱）。

**建议**：不搬 MessageBus；提炼批内排序 + 工具参数 `wait_for_previous`（delegate/terminal 默认串行）。

**Butler 映射**：`butler/core/parallel_tools.py`、`butler/core/tool_batch.py`

---

#### G-P1-5：PolicyEngine 增强（Shell 解析 + MCP 通配）

**Gemini**：`policy-engine.ts` — shell-quote 解析、重定向检测、`*mcp_server_*`、确认后 `updatePolicy`。

**Butler**：`permissions.py` YAML allow/deny/ask，**无 argv 级 shell 分解**。

**建议**：terminal allowlist 扩展子命令/路径模式；MCP 通配；微信用户确认视为 ASK→ALLOW（对标 `isClientInitiated`）。

**Butler 映射**：`butler/permissions.py`、`butler/tools/registry.py`

---

### 4.3 P2 — 体验与质量（按需）

| ID | Gemini | Butler 建议 |
|----|--------|-------------|
| G-P2-1 | `omissionPlaceholderDetector.ts` | `patch` 前检测 `rest of code unchanged` 类懒惰占位 |
| G-P2-2 | `llm-edit-fixer.ts` | patch 失败时辅助模型修 diff（可选） |
| G-P2-3 | `memoryDiscovery.ts` inode 去重 | Skill/MEMORY 加载防大小写 FS 重复 |
| G-P2-4 | `PreCompress` / `BeforeAgent` hooks | 扩展 `gateway/hooks.py` |
| G-P2-5 | `fastAckHelper` steer XML 包裹 | `steer.py` 对用户 steer 做 `<user_input>` 包裹 |
| G-P2-6 | `ContextManager` 图管线 | **仅借鉴 pull-render + 缓存**；勿引入全图引擎 |
| G-P2-7 | `AgentSession` 流重放 | Gateway 出站分段与中断恢复 |
| G-P2-8 | `policyHelpers.ts` 模型策略链 | 增强 `transport/fallback.py` 同族回退说明 |

---

## 5. 不宜照搬（产品边界）

与 [`AGENTS.md`](../../AGENTS.md) 一致：

| 项 | 原因 |
|----|------|
| npm MCP Host 一等公民 | Butler 为可选 `BUTLER_MCP_ENABLED` + 薄客户端，非桌面 CLI 假设 |
| `SandboxManager` 全栈 | 微信场景 `terminal` 默认关 |
| VS Code IDE Companion / 语音 / A2A | 与微信管家无关 |
| 整包 `ContextManager` 图引擎 | 工程量大；百万 token 本地 IDE 场景为主 |
| Conseca safety 全栈 | 合规需求再单独立项 |
| Eval / perf-tests 全量移植 | 运维参考即可，非产品运行时 |

---

## 6. 与现有规划的关系

| 文档 | 关系 |
|------|------|
| [`cc-butler-gap-analysis-2026-05.md`](cc-butler-gap-analysis-2026-05.md) | CC 线束已收口；本报告补 **masking 预算截断、LLM loop、next speaker** 等 |
| [`reference-learning-plan-2026-05.md`](reference-learning-plan-2026-05.md) | 已关闭；Gemini 为**第三条只读对照**（`reference/gemini-cli`，gitignore） |
| [`openclaw-learning-plan-2026-05.md`](openclaw-learning-plan-2026-05.md) | 前置压缩、工具环与 Gemini 部分重叠；落地时避免重复改同一函数 |
| [`v4-architecture.md`](../architecture/v4-architecture.md) | G-P0 落地后更新「上下文经济学」小节 |

---

## 7. 推荐落地顺序

```text
第 1 波（G-P0）
  1. 统一 Tool Output Masking + spill 指针（G-P0-1）
  2. compress 前 functionResponse 预算截断（G-P0-2）
  3. 压缩状态机 + /诊断 字段（G-P0-3）

第 2 波（G-P1）
  4. history 不变式层（G-P1-1）
  5. 可选 LLM loop check + next speaker（G-P1-2、G-P1-3）
  6. parallel_tools 批内排序 / wait_for_previous（G-P1-4）
  7. permissions shell/MCP 规则（G-P1-5）

第 3 波（G-P2，按需）
  G-P2-1 … G-P2-8
```

---

## 8. 验收命令

改 `butler/core` 或 `butler/gateway` 后：

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py tests/test_tool_result_storage.py \
  tests/test_context_pipeline.py tests/test_tool_prune_policy.py -q

# 若改 gateway / 队列
PYTHONPATH=. pytest tests/test_message_queue.py tests/test_gateway_handler.py -q
```

---

## 9. 总结

Gemini CLI 对 Butler 的最大价值在于 **上下文三层经济学**（masking + 压缩前 tool 预算 + 压缩失败状态机）、**调度与策略分离**（Scheduler + PolicyEngine）、**智能止损**（LLM 语义循环 + next speaker）。

Butler 在 **微信多项目、队列 steer、CC 线束、记忆与委派** 上已更强。将上述机制 **零依赖映射** 进现有模块，可在不偏离产品边界的前提下，继续压低长会话 token 与死循环概率。

---

## 10. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：基于 `reference/gemini-cli` 源码与 Butler v4 代码核验 |
