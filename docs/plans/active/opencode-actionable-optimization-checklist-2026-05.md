# Butler 可执行优化清单（基于 OpenCode 深挖）

> **状态**：活跃执行清单（2026-05-26）  
> **来源**：`reference/opencode` 源码深挖 + [`../comparisons/opencode-butler-comparison-report-2026-05.md`](../comparisons/opencode-butler-comparison-report-2026-05.md)  
> **边界**：以 [`../decisions/roadmap-backlog-and-boundaries-2026-05.md`](../decisions/roadmap-backlog-and-boundaries-2026-05.md) 与 [`../../architecture/v4-architecture.md`](../../architecture/v4-architecture.md) 为准  
> **原则**：只提炼算法、权限、状态机与控制面分层；**不**引入 Effect-TS / Drizzle / OpenCode runtime / IDE 桌面壳

---

## 1. 目标

将 OpenCode 中对 Butler v4 **最有迁移价值**、且 **不突破微信管家产品边界** 的能力整理成可执行清单，避免两类误区：

1. 把对照分析当成待办全文复活  
2. 把 OpenCode 的 IDE/桌面产品形态误搬进 Butler

本清单面向 Butler 现有主轴：

- 微信网关
- 自建 Python Agent Loop
- 多项目 / `delegate_task`
- runtime 诊断
- queue mode
- workflow 权限

---

## 2. 执行原则

- 优先抽 **算法与状态机**，不抽 **运行时技术栈**
- 优先增量增强 `butler/core`、`butler/gateway`、`butler/permissions.py`
- 任何涉及 `butler/core` 或 `butler/gateway` 的实施，先跑 AGENTS 指定守门测试
- 与现有边界冲突的项直接标注为 **不做**，不进入实施排期

---

## 3. P1（建议下一步开工）

这些项都具备三个特征：**收益高、迁移成本可控、与当前边界一致**。

> **2026-05-26 收口说明**：`turn-based compaction`、会话批准缓存、`external_directory`、`child_session_key` transcript 已有仓库子集；后续实施重点应放在 **可观测性补齐、剩余边界收口**，而不是引入 OpenCode 运行时或额外平台依赖。

### 3.1 Turn-based 压缩尾 + token 预算 + splitTurn

- [ ] **目标**：将当前偏“消息数/字符”的尾保护升级为按 **turn + token budget** 选择，必要时允许 mid-turn split
- [ ] **收益**：长会话稳定性更高；减少压缩后“保住了最新消息数，但没保住真正重要上下文”的问题
- [ ] **主要改动面**：
  - `butler/core/context_compressor.py`
  - `butler/core/context_pipeline.py`
  - `butler/core/turn_token_budget.py`
- [ ] **验收标准**：
  - 长工具链会话中，最近 2 个 user turn 在预算内优先保留
  - 当最新 turn 过大时，允许从 turn 中部开始保留后半段，而不是整体丢弃
  - `/诊断` 能看见本轮压缩采用了何种尾选择策略
- [ ] **风险提示**：
  - 需要小心和现有 `post_compact_cleanup` 锚点逻辑配合
  - 不能把 `delegate_task` / `patch` 这类高价值消息误裁掉

### 3.2 会话批准缓存（一次 / 始终）

- [ ] **目标**：把当前偏静态的 `ask` 权限升级为运行时批准缓存，支持「允许一次 / 始终允许 / 拒绝」
- [ ] **收益**：减少 Owner 对同类安全工具调用的重复确认；贴近 OpenCode 的交互权限体验
- [ ] **主要改动面**：
  - `butler/permissions.py`
  - `butler/gateway/message_handler.py`
  - `butler/human_gate.py`（如需统一交互）
- [ ] **验收标准**：
  - 同一会话内，批准过的同类安全 pattern 不再重复 ask
  - 「始终允许」有清晰作用域：只限 session / project，不得默认全局放开
  - `/诊断` 或权限日志能显示本次调用命中了缓存批准
- [ ] **风险提示**：
  - 必须保留 revoke/失效机制
  - workflow 的人工审批语义不能被工具批准缓存偷穿透

### 3.3 `external_directory` 等价规则 + shell 路径预检

- [ ] **目标**：把“工作区外路径”从泛化 ask 升级为单独权限语义，并在 shell 执行前做轻量路径预检
- [ ] **收益**：多项目切换和跨目录操作更安全；降低误改外部路径风险
- [ ] **主要改动面**：
  - `butler/permissions.py`
  - `butler/core/path_safety.py`
  - `butler/tools/registry.py`
- [ ] **验收标准**：
  - 对 workspace 外目录的读写/命令访问有独立权限判断
  - shell 工具在简单 `cd` / 文件参数场景下能提取出目标路径并预检
  - 误报存在时优先 ask，不得 silently allow
- [ ] **风险提示**：
  - 不建议引入 `tree-sitter`；优先使用轻量 heuristic / regex
  - Windows/WSL/相对路径需要单测覆盖

### 3.4 `child_session_key` 独立 transcript

- [ ] **目标**：让 `delegate_task` 的子会话拥有独立 transcript，而不是仅靠父会话内嵌结果表示
- [ ] **收益**：真正支持 resume、追责、`/任务` 深看、错误回放
- [ ] **主要改动面**：
  - `butler/core/session_transcript.py`
  - `butler/core/delegate_context.py`
  - `butler/runtime/task_store.py`
  - `butler/report.py`
- [ ] **验收标准**：
  - 子任务有独立 transcript 文件或独立 transcript 命名空间
  - 父任务能引用子 transcript 摘要，但不替代子 transcript 本身
  - `/任务`、`/详细` 能定位到子会话历史
- [ ] **风险提示**：
  - 不能破坏当前 `child_session_key` 约定
  - 需要明确父子 transcript 的清理与保留策略

---

## 4. P2（增强项）

这些项值得做，但应在 P1 收口后再推进。

### 4.1 Overflow 后 replay / continue

- [ ] **目标**：在 overflow / 413 后，不是简单失败，而是压缩后回放关键 user turn 再续跑
- [ ] **主要改动面**：
  - `butler/core/reactive_compact.py`
  - `butler/core/agent_loop.py`
  - `butler/core/session_transcript.py`
- [ ] **验收标准**：
  - overflow 后能记录 `overflow_replay` 类事件
  - 用户感知是“继续当前任务”，而不是重新开始
- [ ] **风险提示**：
  - replay 点选错会导致重复执行或语义漂移

### 4.2 Compaction 作为 Loop 显式任务

- [ ] **目标**：把压缩从隐含分支提升为显式 loop 状态，让 transcript / `/诊断` 能精确表达“正在压缩 / 压缩失败 / 压缩完成”
- [ ] **主要改动面**：
  - `butler/core/agent_loop.py`
  - `butler/core/loop_types.py`
  - `butler/core/session_transcript.py`
- [ ] **验收标准**：
  - transcript 有明确 `compact_scheduled`、`compact_started`、`compact_done`、`compact_failed`
  - `/诊断` 能区分普通重试与压缩任务

### 4.3 Cache policy 自动断点

- [ ] **目标**：将 Anthropic/Bedrock 这类 provider 的 prompt cache 断点下沉到 transport 侧自动处理
- [ ] **主要改动面**：
  - `butler/transport/*`
  - `butler/core/cache_safe_delegate.py`
  - `butler/core/context_budget.py`
- [ ] **验收标准**：
  - system / latest user / tools 边界可自动布点
  - `/诊断` 能看到 cache write / read 变化
- [ ] **风险提示**：
  - 只应影响成本与性能，不得改变消息语义

### 4.4 Hook：`pre_compact` / `pre_tool_execute`

- [ ] **目标**：在现有 HookBus 基础上增加更稳定的“压缩前 / 工具执行前”插点
- [ ] **主要改动面**：
  - `butler/gateway/hooks.py`
  - `butler/core/context_pipeline.py`
  - `butler/core/tool_batch.py`
- [ ] **验收标准**：
  - Hook 顺序文档化
  - 失败时行为明确：跳过、阻断、仅记录

### 4.5 可选 post-edit format

- [ ] **目标**：为写文件后自动格式化提供 env 开关，而不是默认启用
- [ ] **主要改动面**：
  - `butler/tools/registry.py`
  - 相关格式化辅助模块
- [ ] **验收标准**：
  - 默认关闭
  - 不存在 formatter 时优雅降级

---

## 5. 明确不做

这些项来自 OpenCode，但**不符合 Butler 当前产品边界**，不进入实施清单。

- [ ] **不做**：SQLite Message + Part 全量替换 `transcript.jsonl`
- [ ] **不做**：`SyncEvent + projector` 全栈事件溯源
- [ ] **不做**：Effect HttpApi / OpenCode runtime 整体迁移
- [ ] **不做**：第二套 `apply_patch` DSL
- [ ] **不做**：PTY / WebSocket / Electron / TUI 壳
- [ ] **不做**：LSP、Share URL、全量 MCP Host

**原因统一口径**：

1. 与微信管家产品形态不一致  
2. 与既有边界文档冲突  
3. 迁移成本远大于边际收益  

---

## 6. 推荐开工顺序

1. `turn-based compaction`
2. `会话批准缓存`
3. `external_directory + shell 预检`
4. `child_session_key 独立 transcript`
5. `overflow replay`

推荐原因：

- 前 4 项都能在现有 Python 架构内增量完成
- 都能直接改善微信长会话、权限交互、多项目与委派体验
- 都不要求先改底层存储模型

---

## 7. 变更守门

若后续实施本清单中涉及 `butler/core` 或 `butler/gateway` 的项，实施前后至少执行：

```bash
cd /path/to/WFXM
PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py tests/test_runtime_metrics.py tests/test_tool_result_storage.py -q
PYTHONPATH=. pytest tests/test_message_queue.py tests/test_gateway_queue_command.py tests/test_p2_workflow_permissions.py tests/test_gateway_handler.py -q
```

若改动委派 / transcript / permissions，补充对应专项用例：

- `tests/test_cc_p3_p4_features.py`
- `tests/test_gateway_handler.py`
- `tests/test_message_queue.py`

---

## 8. 一句话结论

OpenCode 最值得 Butler 学的不是 Bun/Effect/SQLite，而是 **上下文经济学、运行时权限缓存、子任务状态管理**；最该坚持不学的是它为 IDE/桌面产品形态服务的那整层运行时和壳。
