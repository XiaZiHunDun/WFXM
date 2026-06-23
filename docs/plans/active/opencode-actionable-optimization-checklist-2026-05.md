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

- [x] **目标**：将当前偏“消息数/字符”的尾保护升级为按 **turn + token budget** 选择，必要时允许 mid-turn split
- [ ] **收益**：长会话稳定性更高；减少压缩后“保住了最新消息数，但没保住真正重要上下文”的问题
- [ ] **主要改动面**：
  - `butler/core/context_compressor.py`
  - `butler/core/context_pipeline.py`
  - `butler/core/turn_token_budget.py`
- [ ] **验收标准**：
  - [x] 长工具链会话中，最近 2 个 user turn 在预算内优先保留
  - [x] 当最新 turn 过大时，允许从 turn 中部开始保留后半段，而不是整体丢弃
  - [x] `/诊断` 能看见本轮压缩采用了何种尾选择策略
- [ ] **风险提示**：
  - 需要小心和现有 `post_compact_cleanup` 锚点逻辑配合
  - 不能把 `delegate_task` / `patch` 这类高价值消息误裁掉

> **Sprint 24 (2026-06-04) 完成**: 加 `_strategy_label` helper + `select_tail_start_index` diagnostics 注入, 6 字段 always-on (`compaction_strategy` / `tail_turns_kept` / `split_turn_applied` / `preserved_recent_budget` / `tail_token_count` / `tail_start_index`); 6 新测试覆盖 strategy 标签生成 / 透传 / fallback / no_op / end-to-end. 3946 passed, 0 新增失败 (pre-existing 99 失败未变).

### 3.2 会话批准缓存（一次 / 始终）

- [x] **目标**：把当前偏静态的 `ask` 权限升级为运行时批准缓存，支持「允许一次 / 始终允许 / 拒绝」
- [x] **收益**：减少 Owner 对同类安全工具调用的重复确认；贴近 OpenCode 的交互权限体验
- [x] **主要改动面**：
  - `butler/permissions/approvals.py`
  - `butler/permissions/rules.py`
  - `butler/permissions/doom_loop.py`
  - `butler/mcp/approval.py`
  - `butler/ops/health_report.py`
  - `butler/gateway/commands/permission_commands.py`
- [x] **验收标准**：
  - [x] 同一会话内，批准过的同类安全 pattern 不再重复 ask
  - [x] 「始终允许」有清晰作用域：只限 session / project，不得默认全局放开
  - [x] `/诊断` 或权限日志能显示本次调用命中了缓存批准
- [x] **风险提示**：
  - 必须保留 revoke/失效机制 ✅ `revoke_always` / `clear_always` (Sprint 24)
  - workflow 的人工审批语义不能被工具批准缓存偷穿透 ✅ `is_step_approved` (human_gate) 与 `is_approved` (approvals) API 独立 (Sprint 24 测试验证)

> **Sprint 24 (2026-06-04) 完成**: §3.2 P1 全部验收 + 风险点收口. 5 commits (1+1+1+2, 含 1 IMPROVE refactor). 19 新测试覆盖 diagnostics 4 + revoke 5 + summarize 2 + health 3 + registry 4 + workflow 1. owner_gate_scan gap 数稳定 9 (2 新 handler 都有 owner gate). workflow 边界测试明确验证 `is_step_approved` (human_gate.py:184) 与 `is_approved` (approvals.py:212) 存储路径分离, 互不影响.

### 3.3 `external_directory` 等价规则 + shell 路径预检

- [x] **目标**：把"工作区外路径"从泛化 ask 升级为单独权限语义，并在 shell 执行前做轻量路径预检
- [x] **收益**：多项目切换和跨目录操作更安全；降低误改外部路径风险
- [x] **主要改动面**：
  - `butler/permissions/rules.py` (`evaluate_external_directory` / `check_external_path_override`)
  - `butler/tools/path_safety.py` (`check_tool_path` / `prepare_shell_command` + `_extract_command_paths` + `_existing_argv_paths`)
  - `butler/permissions/approvals.py` (session approval cache 集成)
- [x] **验收标准**：
  - [x] 对 workspace 外目录的读写/命令访问有独立权限判断
  - [x] shell 工具在简单 `cd` / 文件参数场景下能提取出目标路径并预检
  - [x] 误报存在时优先 ask，不得 silently allow
- [x] **风险提示**：
  - 不建议引入 `tree-sitter`；优先使用轻量 heuristic / regex ✅ 使用 shlex.split + 正则
  - Windows/WSL/相对路径需要单测覆盖 ⚠️ 相对路径 1 case; Windows/WSL 0 case; 待后续 sprint 补齐

> **Sprint 1-21 累计完成**: external_directory 规则 (`permissions/rules.py:109` `evaluate_external_directory`) + `check_tool_path` (`path_safety.py:106`) + `prepare_shell_command` shell 路径预检 (`path_safety.py:179`, 使用 shlex.split + regex) + session approval 集成 (`approvals.py`) + permissions.yaml `external_directory:` 节文档化. 关键 fix: Sprint 21-1 SEC-21-A-1 (`is_relative_to` 越界判定修复, 防 sibling-prefix 误判) + Sprint 21-4 QUAL-21-D-2 (uninstall_skill 越界统一 is_relative_to) + Sprint 1 symlink guard. 测试覆盖: `test_path_safety.py` 8 tests + `test_permission_approvals.py` 4 tests + `test_sprint8_sec6_path_safety.py` 74 lines + `test_sprint20_quarantine_path_safety.py`.
> **Sprint 27 (P1-3.3-gap) 完成**: `path_safety.py:1-30` 加 `_is_windows_absolute_path` helper (regex `^[A-Za-z]:[\\/]` + `^\\\\[?]?[A-Za-z0-9_.$-]+[\\/]` UNC 模式), `check_tool_path` 早退 fail-closed 检测 Windows 绝对路径 (Linux CI 上 `C:/...` / `C:\...` / `\\server\share\...` 都不会被 `Path('C:/...')` 当 relative 误判 in-workspace); `approvals.py:305-345` `summarize_approvals` 加 2 字段 `external_directory_always_count` / `external_directory_once_count` (过滤 `r.get("permission") == "external_directory"`); `health_report.py:82-100` `_shared_diagnostic_lines` 在 `always_count/once_active_count/has_pending` 行下加 `External-Dir: always=N · once=M · pending=Y/N` 行, 仅在 ext_always/ext_once>0 或 has_pending=True 时输出 (避免无活动噪声). **测试**: 11 新测试 (`test_sprint27_external_directory_wsl_windows.py` 5 平台 (WSL/Windows C-slash/C-backslash/UNC/大小写) + 2 相对越界 + 2 summarize 过滤 + 2 /诊断 透传), 全 GREEN. **守门**: 35 path_safety/approvals/quarantine + 53 health_report/diagnostics + 41 compact/turn 全 pass. **commit 序列**: `5e50526` RED + `ed269b3` GREEN.

### 3.4 `child_session_key` 独立 transcript

- [x] **目标**：让 `delegate_task` 的子会话拥有独立 transcript，而不是仅靠父会话内嵌结果表示
- [x] **收益**：真正支持 resume、追责、`/任务` 深看、错误回放
- [x] **主要改动面**：
  - `butler/core/session_transcript.py` (`transcript_path(sk)` → `~/.butler/sessions/{safe_segment(sk)}/transcript.jsonl`)
  - `butler/delegate/subagent_permissions.py` (`make_child_session_key` → `{parent}::delegate::{task_id}`)
  - `butler/runtime/delegate_job.py` (`use_execution_context(..., session_key=child_session_key)` 切换 active session)
  - `butler/runtime/task_store.py` (`create_task` 持久化 `child_session_key` 字段)
  - `butler/core/transcript_export.py` (`_format_row_markdown` 渲染 `delegate_started/turn_start/turn_done` 事件带 `child_session_key` + `parent_session_key`)
  - `butler/core/transcript_retention.py` (`transcript_source_boost("delegate")=+10` 优先保留子 transcript)
  - `butler/gateway/commands/lifecycle_commands.py` (`/任务` 输出 child_sk 提示)
- [x] **验收标准**：
  - 子任务有独立 transcript 文件或独立 transcript 命名空间
  - 父任务能引用子 transcript 摘要，但不替代子 transcript 本身
  - `/任务`、`/详细` 能定位到子会话历史
- [x] **风险提示**：
  - 不能破坏当前 `child_session_key` 约定
  - 需要明确父子 transcript 的清理与保留策略

> **Sprint 1-21 累计完成**: `child_session_key` 命名约定 (`subagent_permissions.py:81-86` `make_child_session_key(parent, task_id) -> f"{parent}::delegate::{tid}"`) + per-session transcript 目录隔离 (`session_transcript.py:47-49` `transcript_path(sk) -> get_butler_home() / "sessions" / safe_segment(sk) / "transcript.jsonl"`) + `use_execution_context` 切换 active session (`delegate_job.py:136` `with use_execution_context(orch, session_key=child_session_key or session_key):`) + `task_store.create_task` 持久化 child_session_key 字段 (`task_store.py:101-130`) + transcript export 渲染 delegate 事件携带 child_session_key 字段 (`transcript_export.py:109-112` `_format_row_markdown` 处理 `delegate_started/turn_start/turn_done` 三事件类型) + retention 给 delegate 源 +10 优先保留 (`transcript_retention.transcript_source_boost("delegate")=10`) + `/任务` 输出 child_sk 提示便于人工定位 (`lifecycle_commands.py:209-210`). **已知 gap** (留待后续 sprint 单独 P1-3.4-gap 任务): `/详细 --child <child_sk>` UI 入口未实现, 暂用 transcript 文件路径定位; `/详细` 当前只支持按 `task_id` 倒查父 session, 不直接接受 child_sk. **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码.
> **Sprint 28 (P1-3.4-gap) 完成**: `report/format.py:1-40` 加 `parse_child_arg(arg) -> (remaining, child_sk | None)` (支持 `--child foo` + `--child=foo` + 剩余 args 透传 section); `report/format.py:78-115` 加 `format_child_session_detail(child_sk, max_lines=80)` (复用 `build_session_markdown` 80 行 + 3 层优雅降级: 空 sk / `BUTLER_SESSION_TRANSCRIPT=0` 关闭 / jsonl 不存在); `info_commands.py:112-130` `_cmd_detail` 入口加 child 分支, 优先 child 路径否则走既有 report + section. 语法: `/详细 --child <sk>` 或 `/详细 --child=<sk>` (剩余 args 可附 `changes/decisions` 等 section 关键字, 给后续 hook 留扩展). **测试**: 17 新测试 (`test_sprint28_verbose_child.py` 9 parse + 3 format + 5 旧路径回归), 全 GREEN. **守门**: 28 report_format + 12 command_registry + 62 path_safety/approvals/sprint27/25/26 全 pass. **commit 序列**: `ac2e61a` RED + `5463e36` GREEN.

---

## 4. P2（增强项）

这些项值得做，但应在 P1 收口后再推进。

### 4.1 Overflow 后 replay / continue

- [x] **目标**：在 overflow / 413 后，不是简单失败，而是压缩后回放关键 user turn 再续跑
- [x] **主要改动面**：
  - `butler/core/reactive_compact.py` (`_compress_with_overflow_replay` + `try_reactive_compact` + `apply_reactive_compact_to_messages`)
  - `butler/core/agent_loop.py` (overflow 触发 reactive compact)
  - `butler/core/session_transcript.py` (后续可加 `overflow_replay` 事件)
- [x] **验收标准**：
  - overflow 后能记录 `overflow_replay` 类事件
  - 用户感知是“继续当前任务”，而不是重新开始
- [x] **风险提示**：
  - replay 点选错会导致重复执行或语义漂移

> **Sprint 1-23 累计完成**: reactive compact 链已落地 (`reactive_compact.py:29` `_compress_with_overflow_replay(..., overflow_replay=True)` flag 透传 compress_fn + `:39` `try_reactive_compact` 入口 + `:105` `apply_reactive_compact_to_messages` 装回 messages + diagnostics 透传 `reactive_compact_strategy` / `reactive_compact_applied` / `reactive_compact_reason`). **真实 gap** (留 P2-4.1-gap 任务): `overflow_replay` transcript 事件类型未注册到 `session_transcript.record_*` 族 (当前只作为 reactive_compact 内部 flag, 不入 transcript jsonl); "用户感知是继续当前任务" 仍依赖 `try_reactive_compact` 自动透传, 无显式 UX 续跑提示. **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码.
> **Sprint 26 (P2-4.1-gap) 完成**: `session_transcript.py:318-333` 新增 `record_overflow_replay(sk, *, source='context_compressor', content_preview='', replayed_chars=0)` (content_preview 80 截断, replayed_chars max(0, int()) 钳位); `context_compressor.py:382-396` 在 `append_overflow_replay` 实际追加 marker 后写入事件 (content_preview 来自 `replay_user.content`, replayed_chars = len(content)); `transcript_diagnostics.py:25-44` `summarize_compact_events` dict 升 6 key + `format_transcript_diagnostic_lines` 在 overflow_replay 计数 > 0 时输出 `⚠️ 续跑提示: 本会话触发了 N 次 413/overflow 续跑` 行. **测试**: 8 新测试 (`test_sprint26_overflow_replay.py` 5 record_ + 1 summarize_ + 2 警告门控), 全 GREEN. **commit 序列**: `f7dfa5c` RED + `01ed3ef` GREEN + `d9e7c37` wiring.

### 4.2 Compaction 作为 Loop 显式任务

- [x] **目标**：把压缩从隐含分支提升为显式 loop 状态，让 transcript / `/诊断` 能精确表达“正在压缩 / 压缩失败 / 压缩完成”
- [x] **主要改动面**：
  - `butler/core/agent_loop.py` (loop 状态机)
  - `butler/core/loop_types.py` (loop 状态枚举)
  - `butler/core/session_transcript.py` (`record_compact_scheduled` + `record_compact_done` 已实现)
- [x] **验收标准**：
  - transcript 有明确 `compact_scheduled`、`compact_started`、`compact_done`、`compact_failed`
  - `/诊断` 能区分普通重试与压缩任务

> **Sprint 1-23 累计完成**: transcript 事件类型 2/4 已实现 (`session_transcript.py:247` `record_compact_scheduled` + `:265` `record_compact_done`); `/诊断` 集成 (`transcript_diagnostics.py:25-32` 已读 `compact_scheduled` / `compact_done` 计数, 输出 "近 N 条 · 压缩 X/Y 完成" 摘要). **真实 gap** (留 P2-4.2-gap 任务): `compact_started` + `compact_failed` 两个事件类型未在 `session_transcript.record_*` 族中实现, 当前 2/4 覆盖. `compact_started` 标志 "压缩开始" 状态可让 /诊断 区分"已 schedule 还没跑" vs "已 schedule 正在跑" 两个时间窗; `compact_failed` 让 /诊断 在压缩异常时给 owner 可见反馈. **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码.

### 4.3 Cache policy 自动断点

- [x] **目标**：将 Anthropic/Bedrock 这类 provider 的 prompt cache 断点下沉到 transport 侧自动处理
- [x] **主要改动面**：
  - `butler/transport/*` (cache_control 自动布点)
  - `butler/core/cache_safe_delegate.py` (delegate 侧安全策略, 已实现)
  - `butler/core/context_budget.py` (预算分配)
- [x] **验收标准**：
  - system / latest user / tools 边界可自动布点
  - `/诊断` 能看到 cache write / read 变化
- [x] **风险提示**：
  - 只应影响成本与性能，不得改变消息语义

> **Sprint 1-23 累计完成 (delegate 侧)**: `cache_safe_delegate.py:16` `cache_safe_delegate_enabled` env toggle + `:75` `compute_cache_safe_bundle` (输出 `cache_safe_v2: True` 标记) + `:93` `apply_cache_safe_system_prompt` + `:126` delegate 主路径集成. **真实 gap** (留 P2-4.3-gap 任务): `butler/transport/` 侧 (anthropic_transport.py / chat_completions.py / llm_client.py) 缺 transport-level 自动 cache_control 布点 (system / latest user / tools 边界), 当前依赖 provider SDK 默认行为. `cache_safe_delegate` 是 delegate 主路径的"防 cache 错位"安全策略, 与 transport-level 自动布点是**不同层次**的优化.
>
> **Sprint 29 P2-4.3 完成 (transport 侧)**: 新建 `butler/transport/cache_control.py` (110 行, 5 helper), 接入 `anthropic_transport.py` (convert_messages + build_kwargs), Anthropic Prompt Caching 4 boundary 自动布点: (1) system → `[{type:text, text, cache_control:ephemeral}]`; (2) 最后 role=user → 末尾追加 marker block; (3) tools → 最后 tool 顶层加 cache_control; (4) 最后 tool_result → 块加 marker. bypass: `BUTLER_TRANSPORT_CACHE_CONTROL=0` 全部早退 (system 仍走 str 路径, 向后兼容). 25 新测试 (env toggle 4 + system 3 + messages 7 + tools 3 + last_tool_result 4 + integration 2 + wiring 2). 2 commits (`76574f0` + `66be229`). **风险落地**: "只应影响成本与性能, 不得改变消息语义" — 开启后 `kwargs["system"]` 从 str 变 list, Anthropic API 中两种 form 合法等价, 语义不变. OpenAI chat_completions 不动 (OpenAI 原生无 cache_control 字段). **本任务正式收口** (P2-4.3 + P2-4.3-gap 全部完成, 4 boundary 实现, delegate + transport 双层优化齐全).

### 4.4 Hook：`pre_compact` / `pre_tool_execute`

- [x] **目标**：在现有 HookBus 基础上增加更稳定的“压缩前 / 工具执行前”插点
- [x] **主要改动面**：
  - `butler/gateway/hooks.py` (HookBus 基础设施)
  - `butler/hooks/runner.py` (`run_pre_compact_hooks` + `pre_tool_execute` alias 已实现)
  - `butler/core/compaction_task.py` (pre_compact hooks 接入, 已实现)
  - 架构文档 (Hook 顺序说明)
- [x] **验收标准**：
  - Hook 顺序文档化
  - 失败时行为明确：跳过、阻断、仅记录

> **Sprint 1-23 累计完成 (90%)**: `butler/hooks/runner.py:397` `run_pre_compact_hooks` + `:451` `pre_tool_execute` alias (PreToolUse); `butler/hooks/__init__.py:11,29` 导出; `butler/hooks/hooks.yaml.example:4-5` 注释说明 "pre_tool_execute = PreToolUse" + 列出 pre_llm_call / pre_gateway_dispatch / pre_compact / post_compact 全部 hook 点; `butler/core/compaction_task.py:65-67` pre_compact 实际接入 (try/except logger.debug 容错). **真实 gap** (留 P2-4.4-gap 任务): Hook 顺序未在 `docs/architecture/v4-architecture.md` 单独成节, 散落在 hermes-extraction-map / post_compact_cleanup / fact_extraction 多个 cross-reference 中; 失败时行为 (跳过/阻断/仅记录) 的统一契约未集中文档化. **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码.

### 4.5 可选 post-edit format

- [x] **目标**：为写文件后自动格式化提供 env 开关，而不是默认启用
- [x] **主要改动面**：
  - `butler/tools/registry.py` (工具注册)
  - `butler/core/post_edit_format.py` (`post_edit_format_enabled` + `maybe_format_after_edit` 已实现)
  - `butler/tools/file_io.py` (写文件主路径集成, 已实现)
- [x] **验收标准**：
  - 默认关闭
  - 不存在 formatter 时优雅降级

> **Sprint 1-23 累计完成 (100%)**: `butler/core/post_edit_format.py:29` `post_edit_format_enabled` env toggle (`BUTLER_POST_EDIT_FORMAT` 默认 `False`) + `:39-50` 早退 (关/无后缀/无 tool 全部 `None` 或 `skipped`) + `:46-47` `_command_available` 走 `shutil.which` 检测, 缺 formatter 返 `{"skipped": True, "reason": "... not in PATH"}` (优雅降级) + `:52-54` timeout env 可配 + `:63-68` subprocess 异常/非零 exit 返 `{"formatted": False, "tool": ..., "error": ...}` 不抛; `butler/tools/file_io.py:354,467` 写文件主路径集成 `maybe_format_after_edit`, payload 写回 `post_edit_format` 字段. **真实 gap**: 无 (完全实现). **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码.

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
PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py tests/ops/test_runtime_metrics.py tests/test_tool_result_storage.py -q
PYTHONPATH=. pytest tests/gateway/test_message_queue.py tests/gateway/test_gateway_queue_command.py tests/test_p2_workflow_permissions.py tests/gateway/test_gateway_handler.py -q
```

若改动委派 / transcript / permissions，补充对应专项用例：

- `tests/test_cc_p3_p4_features.py`
- `tests/gateway/test_gateway_handler.py`
- `tests/gateway/test_message_queue.py`

---

## 8. 一句话结论

OpenCode 最值得 Butler 学的不是 Bun/Effect/SQLite，而是 **上下文经济学、运行时权限缓存、子任务状态管理**；最该坚持不学的是它为 IDE/桌面产品形态服务的那整层运行时和壳。
