# OpenCode ↔ Butler v4 对照分析报告

> **日期**：2026-05-25  
> **对照源**：`reference/opencode`（本地 gitignore，不嵌入运行时）  
> **Butler 基线**：[`v4-architecture.md`](../architecture/v4-architecture.md)、[`opencode-learning-plan-2026-05.md`](opencode-learning-plan-2026-05.md)（P0–P2 已落地）  
> **原则**：只借鉴设计/理论，不引入 Effect-TS / Drizzle / AI SDK / npm 插件 Host  
> **并行主线**：CC 线束见 [`cc-butler-gap-analysis-2026-05.md`](cc-butler-gap-analysis-2026-05.md)

---

## 1. 执行摘要

| 维度 | OpenCode | Butler v4 |
|------|----------|-----------|
| 主场景 | 本地/IDE 编码助手（TUI + `opencode serve` HTTP） | 微信远程管家 + 多项目 Lead |
| 会话模型 | SQLite **Message + Part**（tool/reasoning/compaction/subtask…） | 扁平 chat messages + **JSONL transcript** 取证 |
| 一致性 | SyncEvent 事件溯源 → projector 写库，单 writer + `seq` 全序 | 进程内 `session_lock`，无多客户端回放 |
| 权限 UX | `allow` / `ask` / `deny`，`ask` 可 **一次/始终** 批准并持久化 | YAML last-match + Owner 门控；`ask` 多为静态提示 |
| 委派 | `task` 工具 → **子 Session**（`parentID`），可后台 + `task_status` | `delegate_task` 进程内子 Loop + `child_session_key` |
| 产品边界 | MCP/LSP/格式化/分享 URL 一等公民 | 刻意不做 MCP Host、HTTP 多客户端、公开分享 |

**结论**：

- **已对齐**（2026-05-25）：压缩模板、backward prune、cache overflow 计费、last-match 权限、doom loop 检测、instruction walk-up、session todos、子代理 key、transcript compact 事件等（见 §3）。
- **最值得继续抽的理论**：① 按 **turn** 的上下文经济学；② 交互式权限 → **微信批准缓存**；③ **委派子会话持久化**；④ 压缩/overflow **显式状态机**（不必 SQLite）。
- **不必照搬**：事件溯源全栈、HTTP 服务、MCP/LSP、公开分享、文件系统 snapshot revert。

---

## 2. 定位差异：两套产品哲学

OpenCode 的核心理论：**「可同步的会话数据库 + 细粒度 Part 状态机 + 交互式权限」**。

Butler 的核心理论：**「微信单写者 + 上下文经济学 + 多项目编排」**。

两者不是替代关系；在 Butler 产品边界内抽取设计，不搬迁 OpenCode 运行时（学习规划 **D1**）。

---

## 3. 已提炼并落地（避免重复造轮子）

来源：[`opencode-learning-plan-2026-05.md`](opencode-learning-plan-2026-05.md) §3–§4，**2026-05-25 收口**。

| OpenCode 概念 | Butler 模块 | 配置 / 命令 | 备注 |
|---------------|-------------|-------------|------|
| 压缩摘要模板 | `butler/core/compaction_prompt.py` | `BUTLER_COMPACTION_USE_OPENCODE_TEMPLATE` | 对齐 `SUMMARY_TEMPLATE` |
| 工具输出 backward prune（20k/40k） | `butler/core/tool_output_prune.py` | `BUTLER_TOOL_PRUNE_BACKWARD_*` | 与 `compaction.ts` 常量一致 |
| Overflow 含 cache | `butler/core/context_budget.py` | `/诊断` 上下文行 | `usage_billable_tokens` |
| last-match 权限 | `butler/permissions.py` | `.butler/permissions.yaml` | 后写规则覆盖前写 |
| doom loop | `butler/tool_guardrails.py` | `BUTLER_DOOM_LOOP_THRESHOLD`（0=关） | **行为不同**：硬阻断 vs OpenCode `ask` |
| 子代理权限 | `butler/delegate_subagent_permissions.py` | `delegate_subagent` in YAML | deny 列表 + 角色 allowlist |
| task / child session | `butler/runtime/task_store.py`、`report.py` | `/任务`、`/详细` | `child_session_key` = `{session}::delegate::{task_id}` |
| read 触发 instruction walk-up | `butler/core/instruction_walkup.py` | `BUTLER_INSTRUCTION_WALKUP_*` | 对齐 `instruction.ts` |
| Transcript compact 事件 | `butler/core/session_transcript.py` | — | `compact_scheduled` / `compact_done` |
| Post-commit 副作用队列 | `butler/core/post_commit.py` | — | 记忆/post_session 后 flush |
| 会话 Todo replace-all | `butler/core/session_todos.py` | `/待办`；`session_todos_*` 工具 | JSON 非 SQLite |
| Hook 有序 mutate | `butler/gateway/hooks.py` | — | `trigger_hooks_mutating` |

**仍明确暂缓**：

- 主 Loop 入队 **CompactionPart**（改 loop 入队语义）。
- 完整 SQLite message/part + SyncEvent projector（jsonl 够用则不做了）。

---

## 4. 分领域对照

### 4.1 会话 / Message / Part 与事件溯源

**OpenCode**

- 领域模型：Session → Message (info) → Part[]（SQLite）。
- Part 类型：`text`、`tool`、`file`、`reasoning`、`compaction`、`subtask`、`snapshot`、`patch` 等。
- SyncEvent：事件在 **变更前** 发出，projector 落库；`seq` 单调递增，**单 writer** 即可全序回放（见 `packages/opencode/src/sync/README.md`）。

**Butler**

- `session_transcript.py`：append-only 取证（compact/todo/queue 等），**非**可重放状态机。
- Agent Loop 使用 OpenAI 风格扁平 messages（`agent_loop.py`）。
- 并发：`gateway/session_registry.py` 的 `session_lock`（每 `session_key` 单活跃 turn）。

**差距与可提炼**

| 优先级 | 建议 |
|--------|------|
| P2 | 为 tool/compact/overflow 增加有序、可重放的事件类型，强化 `/诊断` 与 RCA |
| P2 | **Compaction 作为 Loop 一等任务**（OpenCode `CompactionPart` + `prompt.ts` 处理 `task.type === "compaction"`） |
| 暂缓 | 完整 SQLite + SyncEvent（学习规划已记录） |

---

### 4.2 上下文经济学：压缩 / Prune / Overflow

**OpenCode**

- `overflow.ts`：`usable()` = context − reserved（默认 20k）；`isOverflow()` 计 **input + output + cache.read + cache.write**。
- `compaction.ts`：按 **turn** 选尾（`tail_turns` 默认 2）、`preserve_recent_tokens`（2k–8k 或 25% usable）、可 **splitTurn**；prune 常量 `PRUNE_MINIMUM=20_000`、`PRUNE_PROTECT=40_000`；每轮 processor 后 fork prune。

**Butler**

- 已落地：`tool_output_prune.py`、`tool_prune_policy.py`、`context_compressor.py`、`preemptive_compact.py`、`reactive_compact.py`、`post_compact_cleanup.py`。
- `context_budget.usage_billable_tokens` 已与 OpenCode overflow 对齐。
- **部分差异**：尾保护偏 **消息数/字符**，非 turn + token 预算；prune 主要在 pipeline 内，非每 loop step 后必跑。

**差距与可提炼（P1 高价值）**

1. **Turn-based 尾选择** + token 预算 + 可选 mid-turn split。
2. **Overflow 后 replay/continue**（OpenCode `processCompaction` overflow 分支），减少微信侧上下文「断片」。
3. 输出预留与 `compaction.reserved` 概念对齐，降低「计费未满但 API 413」。

---

### 4.3 权限模型

**OpenCode**

- `packages/core/src/permission.ts`：`findLast` 匹配 `(permission, pattern)`，默认 **ask**。
- 运行时：`permission.ask()` → once / always / reject；`always` 写入 `approved[]` 并解除同 session pending。
- 文档：`external_directory`（工作区外路径）、`doom_loop`（默认 ask）。
- 子代理：`subagent-permissions.ts` 三层（父 agent edit deny → session deny + external → 默认 deny todowrite/task）。

**Butler**

- `permissions.py`：YAML last-match；`workflow_steps` 步骤白名单；plan_mode；子代理 `delegate_subagent_permissions.py`。
- `ask` → 多为「需 Owner 确认后重试」，**无** 会话级批准缓存。

**差距与可提炼**

| 优先级 | 建议 | 微信映射 |
|--------|------|----------|
| P1 | 会话批准缓存 | `~/.butler/sessions/<key>/approvals.json`；「允许一次 / 始终允许」 |
| P1 | `external_directory` 等价规则 | 与 workspace 沙箱互补 |
| P2 | 子代理转发父 session edit deny + external 规则 | 对齐 OpenCode #26514 类修复 |
| P2 | 可选 `BUTLER_DOOM_LOOP_MODE=ask` | 产品可选；默认保持硬阻断（D3） |

**Butler 保留优势**：`tool_guardrails.py` 除 doom loop 外还有失败重复、read 无进展等，强于 OpenCode 单点检测。

---

### 4.4 Doom loop / 工具护栏

**OpenCode**（`processor.ts`）：最近 3 个 tool part 同 name + 同 JSON input → `permission.ask({ permission: "doom_loop", ... })`。

**Butler**（`tool_guardrails.py`）：`BUTLER_DOOM_LOOP_THRESHOLD`（默认 3）→ **执行前硬阻断**。

决策记录 **D3**：有意与 OpenCode UI Deferred 不同，适配无交互客户端。

---

### 4.5 委派与子 Session

**OpenCode**

- `tool/task.ts`：创建/恢复 `parentID` 子 Session；派生 permission ruleset；可选 **background** + `task_status`。
- `run-state.ts`：父 session abort 可取消子后台任务。

**Butler**

- `delegate_task`：进程内子 Loop；`child_session_key`；`task_store` + `/任务`、`/详细`。
- **差距**：子 Loop 历史非独立会话树；委派基本同步阻塞；父取消未传播到 in-flight delegate。

**差距与可提炼**

| 优先级 | 建议 |
|--------|------|
| P1 | `child_session_key` 下独立 transcript / 消息快照 → 真 resume、审计 |
| P2 | 异步委派 + 完成微信通知 |
| P2 | 父会话取消 → 取消 in-flight delegate |

---

### 4.6 Instructions / Rules walk-up

**OpenCode**（`instruction.ts`）：read 完成后从文件目录向上至 **worktree root**；按 `messageID` claim，每条 assistant 消息最多注入一次。

**Butler**（`instruction_walkup.py`）：read 后注入 AGENTS.md / CLAUDE.md / RULES.md；claim 常按 **session_key**；边界为 **workspace_root**。

**P2**：per-turn claim；worktree-aware stop（若引入 worktree 会话）。

---

### 4.7 会话内 Todo

**OpenCode**：SQLite replace-all；含 priority（high/medium/low）；子代理默认 deny `todowrite`。

**Butler**：`session_todos.py` → `todos.json`；transcript `todo_updated`；**无 priority 字段**。

**P2**：可选 priority；子代理默认 deny session todo 工具（除非角色显式允许）。

---

### 4.8 Hooks / 插件

**OpenCode**：npm + 本地插件；`tool.execute.before`、`experimental.session.compacting`、`experimental.chat.messages.transform` 等。

**Butler**：shell `hooks.yaml` + `gateway/hooks.py` `trigger_hooks_mutating`。

**可提炼（不引入 npm）**：`pre_tool_execute`、`pre_compact` / `post_compact`；文档化 hook 顺序。

---

### 4.9 多项目 / Worktree

**OpenCode**（`specs/project.md`）：单实例多 project；session 带 `directory` / worktree。

**Butler**：`ProjectManager` + 微信 `/切换`（多项目 Lead 为强项）；**无** per-session git worktree。

**P2**：`project.yaml` 可选 `worktree`；委派在隔离 worktree 改代码。

---

### 4.10 Provider / 模型路由

**OpenCode v2**：Catalog 热更新；compaction/title/summary 隐藏 agent 独立模型。

**Butler**：`orchestrator` 角色路由 + `auxiliary_complete`；微信 `/model`。

**P2**：声明式 `compaction_model`；模型 capability 标记（tools/vision）供 delegate 选型。

---

### 4.11 Revert / Share / LSP / Formatters

| 能力 | OpenCode | Butler | 建议 |
|------|----------|--------|------|
| Revert/unrevert + snapshot | 一等公民 | 无 | P3：仅 transcript truncate 轻量回滚 |
| Share 公网 URL | 有 | 无 | 不做；可 P3 导出 markdown |
| LSP | 自动启动 + 工具 | 无 | P3；仅 CLI 本地可考虑 |
| Post-edit format | prettier/ruff/… | 无 | P2；env 开关 |

---

### 4.12 TUI vs Server

**OpenCode**：`opencode serve` 无头 HTTP；TUI/IDE 为客户端；权限 UI 阻塞 Deferred。

**Butler**：微信 gateway + CLI 单体；**刻意不做** HTTP 多客户端（AGENTS.md 产品边界）。

**P2**：强化 `/诊断` 结构化导出（`ops/transcript_diagnostics.py` 已有子集）。

---

## 5. Butler 已领先或应保留的差异

1. **微信网关**：入站队列 now/next/later、`/steer`、出站 bridge。
2. **多项目 Lead**：`project_lead`、runtime jobs、`workflow_steps`（见 [`project-layer-wechat-plan.md`](../architecture/project-layer-wechat-plan.md)）。
3. **工具护栏**：doom loop 之外的失败循环、read 无进展等。
4. **CC 线束**：流式只读预取、cache-safe delegate、reactive 413、`human_gate`（与 OpenCode 并行，见 gap 文档）。
5. **记忆**：分层 MEMORY + post_session（多项目场景强于单 repo 会话压缩）。

---

## 6. 净新增落地优先级

### P1（建议下一步）

| # | 项 | 主要改动面 |
|---|-----|------------|
| 1 | Turn-based 压缩尾 + token 预算 + splitTurn | `context_compressor.py`、`context_pipeline.py` |
| 2 | 会话批准缓存（一次/始终） | `permissions.py`、gateway Owner 话术 |
| 3 | `external_directory` 等价规则 | `permissions.py`、工具路径校验 |
| 4 | `child_session_key` 独立 transcript | `session_transcript.py`、`delegate_context.py` |

### P2（增强可观测与扩展）

| # | 项 |
|---|-----|
| 5 | Compaction 作为 Loop 显式任务 + transcript 状态机 |
| 6 | Overflow 后 continue/replay |
| 7 | Hook：`pre_compact` / `pre_tool_execute` |
| 8 | 可选 post-edit format（env 开关） |
| 9 | Todo priority；子代理默认 deny session todos |

### P3（按需）

| # | 项 |
|---|-----|
| 10 | Git worktree per session |
| 11 | 轻量 transcript revert |
| 12 | 会话导出 markdown（非公开 share） |
| 13 | LSP（仅本地 CLI 模式） |

### 明确不做

- OpenCode 运行时嵌入、npm 插件 Host、HTTP 多客户端网关、公开 session share、完整 snapshot FS revert。

---

## 7. 关键文件索引

### OpenCode（`reference/opencode`）

| 主题 | 路径 |
|------|------|
| 主循环 | `packages/opencode/src/session/prompt.ts` |
| 流式 / doom loop | `packages/opencode/src/session/processor.ts` |
| 压缩 / prune | `packages/opencode/src/session/compaction.ts` |
| Overflow | `packages/opencode/src/session/overflow.ts` |
| 会话互斥 | `packages/opencode/src/session/run-state.ts` |
| 权限核心 | `packages/core/src/permission.py` |
| 权限运行时 | `packages/opencode/src/permission/index.ts` |
| 子代理权限 | `packages/opencode/src/agent/subagent-permissions.ts` |
| 委派 | `packages/opencode/src/tool/task.ts` |
| 指令 walk-up | `packages/opencode/src/session/instruction.ts` |
| 事件溯源 | `packages/opencode/src/sync/README.md` |
| Revert | `packages/opencode/src/session/revert.ts` |
| 多项目 API | `specs/project.md` |
| 中文权限文档 | `packages/web/src/content/docs/zh-cn/permissions.mdx` |

### Butler

| 主题 | 路径 |
|------|------|
| 架构总览 | `docs/architecture/v4-architecture.md` |
| 已落地清单 | `docs/plans/opencode-learning-plan-2026-05.md` |
| CC 线束 | `docs/plans/cc-butler-gap-analysis-2026-05.md` |
| 上下文管线 | `butler/core/context_pipeline.py` |
| Prune | `butler/core/tool_output_prune.py`、`tool_prune_policy.py` |
| 权限 | `butler/permissions.py` |
| 委派 | `butler/delegate_subagent_permissions.py`、`butler/tools/registry.py` |
| 环境变量 | `docs/config/reference.md`、`.env.example` |

---

## 8. 决策记录（延续学习规划）

| # | 结论 |
|---|------|
| D1 | 不嵌入 OpenCode 运行时 |
| D2 | 权限 last-match 为行为约定：YAML **靠后规则优先** |
| D3 | doom loop 默认 **执行前硬阻断**（非 OpenCode Deferred ask） |
| D4 | `child_session_key` 格式 `{session}::delegate::{task_id}` |
| D5 | 本报告 P1–P3 为 **净新增** 建议，实施前需单独开 implementation 条目并补测试 |

---

## 9. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：Agent 会话对照分析落盘 |

---

*对照完成：2026-05-25 · 源码路径以本地 `reference/opencode` 为准*
