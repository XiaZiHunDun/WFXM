# 权限与门控栈（Phase C4）

> **状态**：2026-06-09  
> **性质**：**只描述现状**；Phase C **不改**门控行为（理论 T3/T6/T8 敏感）。  
> **关联**：[`inbound_pipeline.py`](../../butler/gateway/inbound_pipeline.py) · [`human_gate.py`](../../butler/human_gate.py) · [`permissions/rules.py`](../../butler/permissions/rules.py)

---

## 1. 两层：入站 vs 工具执行

```text
微信入站消息
    │
    ▼
[入站管线] owner / human_gate / injection / two_phase …  （Gateway）
    │
    ▼
Agent Loop → 工具调用
    │
    ▼
[工具链] permissions.yaml → danger → approval → execpolicy  （Loop/工具）
```

---

## 2. 入站管线（Gateway）

默认步骤顺序（`build_default_inbound_pipeline()`）：

| 顺序 | 步骤 | 类型 | 模块 | 作用 |
|------|------|------|------|------|
| 1 | `io_guardrail` | guard | `message_pipelines` | I/O 与长度护栏 |
| 2 | `human_gate` | guard | `human_gate` + `owner_gate` | 待确认 workflow `/确认` `/取消` |
| 3 | `injection_guard` | transform | `memory/injection_guard` | 入站文本注入清洗 |
| 4 | `injection_llm` | guard | `human_gate` | 可选 LLM 注入评分 |
| 5 | `bot_loop_guard` | guard | — | 机器人循环防护 |
| 6 | `two_phase_confirm` | guard | `confirm_flags` | 二次确认门控 |
| 7 | `prequeue_interrupt` | guard | 队列 interrupt 模式 |
| 8 | `mcp_profile` | gate | MCP 按消息选 profile |
| 9 | `pre_dispatch_rewrite` | transform | 斜杠/别名改写 |

**Owner 门控**（`owner_gate.is_gateway_owner`）：

- 敏感**斜杠命令**经 `command_registry.require_owner`（如 `/doctor`、`/config`、`/项目 新建`）
- `BUTLER_ENV=prod` 时禁用 `BUTLER_PROJECT_CREATE_OPEN` 越权 bypass
- 身份：`BUTLER_OWNER_WECHAT_ID` / `WECHAT_ALLOWED_USERS`

**Human gate**（`human_gate.py`）：

- Workflow 步骤待 Owner `/确认` 或 `/取消`
- 可选 `BUTLER_WORKFLOW_AUTO_RESUME=1` 确认后自动续跑（见 v4-architecture 体验增强表）

---

## 3. 工具执行链

| 层 | 配置/模块 | 说明 |
|----|-----------|------|
| 项目工具白名单 | `project.yaml` `tools` / `tool_modes` | `allowed_tool_names_for_project` |
| 声明式权限 | `<workspace>/.butler/permissions.yaml` | 工具 allow/deny、**workflow_steps** 步骤级白名单 |
| 终端危险命令 | `tools/terminal_danger.py` | 模式匹配 + `BUTLER_TERMINAL_DANGER_CHECK` |
| 外部目录批准 | `permissions/approvals.py` | 会话 `approvals.json`；`/诊断` 有统计块 |
| Execpolicy | `~/.butler/execpolicy.yaml` + 内置 `builtin_rules.yaml` | 前缀规则；`BUTLER_EXECPOLICY` |
| Workflow 门控 | `human_gate` + `permissions` `workflow_steps` | 与入站 human_gate 联动 |

编排入口注释：`core/tool_orchestrator.py` — Policy → danger → approval → execpolicy（terminal 路径）。

---

## 4. 记忆与安全注入（横切）

| 机制 | 模块 | 定理/前提 |
|------|------|-----------|
| 记忆注入围栏 | `pre_llm_transform`、注入标记 | T4 不污染 transcript |
| PIM 闭集归一化 | `injection_guard` | P-INJ |
| Post-session 写入门控 | `session/post_session` | MA7 |

---

## 5. 改策略时动哪个文件

| 我想… | 改这里 | 勿改 |
|------|--------|------|
| 限制某项目可用工具 | `project.yaml` 或 `.butler/permissions.yaml` | 勿静默扩 `config_service` 白名单 |
| Workflow 某步要审批 | `permissions.yaml` `workflow_steps` + `human_gate` | — |
| 封禁 shell 子命令 | `execpolicy.yaml` 或 env `BUTLER_TERMINAL_DANGER_CHECK` | — |
| 仅 Owner 能发的微信命令 | `command_registry` + `require_owner` | — |
| 运行时改 env 开关 | `/config`（**非**安全类 key） | API Key、终端类见 Sprint 9 不可写列表 |

不可运行时修改的安全/终端类：见 [`config-surfaces.md`](../config/config-surfaces.md) §5。

---

## 6. 诊断与审计

| 入口 | 门控相关内容 |
|------|----------------|
| `/诊断` | 权限批准缓存、external_directory 决策 |
| `/doctor` / `butler doctor` | `security_audit`：terminal 开关、`permissions.yaml` 解析、workflow_steps |
| `/状态` | 当前项目、Lead/Butler 引擎 |

---

## 7. 人工门控 vs「检查点」语义（勿混淆）

仓库里 **gate** 与 **checkpoint** 是两套机制；理论（T6 / 定义 3.17 `Approve`）只要求 **审批前置**，不要求 LangGraph 式执行断点续跑。

### 7.1 人工门控（审批态 — 理论必需）

| 项 | 说明 |
|----|------|
| **目的** | Owner 确认前，带 `requires_approval` 的 workflow 步骤 **不** 调用子 Agent（T6 / P-T6a–d） |
| **持久化** | `~/.butler/human_gates/<session-hash>.json`（pending）+ `*.approved.json`（已批准 `workflow::step_id`） |
| **微信话术** | 待审时提示；Owner 发 `确认` / `取消`（须 `is_gateway_owner`） |
| **续跑** | 默认：再发 `/workflow <name>`；`BUTLER_WORKFLOW_AUTO_RESUME=1` 时确认后自动重跑 workflow |
| **过期** | `BUTLER_GATEWAY_HUMAN_GATE_TTL`（默认 3600s）清除过期 pending |

模块：`butler/human_gate.py`；DAG 回调：`workflows/runner.py` → `task_orchestrator.execute_graph(on_approval=…)`。

**这不是「从第 N 步接着跑」**：批准的是 **权限**，不是 **缓存上一步的子 Agent 输出**。

### 7.2 Workflow 快照 / 检查点（执行进度 — 仅写、诊断用）

| 文件 | 路径 | 写入 | 续跑时是否读取 |
|------|------|------|----------------|
| 逐步 checkpoint | `<workspace>/.butler/workflow_runs/<wf>-checkpoint.json` | 每步 `done` 后（`BUTLER_WORKFLOW_CHECKPOINT=1`，默认开） | **否** |
| 跑完 snapshot | `...-<wf>-latest.json` | workflow 结束时 | **否**（排障 / AgentReport） |
| pause 状态 | `<workspace>/.butler/workflow_pause.json` 或 `~/.butler/workflow_pause/` | gate 阻塞时 `save_workflow_pause` | **否**（`load_workflow_pause` 未接入 runner） |

因此：**再次 `/workflow` 会重新调度整个 DAG**。已通过 gate 的步骤会因 `approved.json` 而 **不再等待确认**，但 **无 `requires_approval` 且上轮已完成的步骤会再执行一遍**（除非步骤自身幂等或由 YAML 设计避免重复副作用）。

### 7.3 上下文压缩 checkpoint（第三类 — 与 workflow 无关）

| 文件 | 路径 | 作用 |
|------|------|------|
| compact checkpoint | `~/.butler/sessions/<session>/compact_checkpoint.json` | 长会话 **micro/auto 压缩** 后保留 model / todos 摘要；`/新对话` 可清理 |

模块：`butler/core/compaction_checkpoint.py`；与 §7.1 审批、§7.2 DAG 进度 **无耦合**。

### 7.4 产品边界与何时考虑增强

| 立场 | 说明 |
|------|------|
| **保持** | 人工门控 + 审批持久化 + 手动/可选 auto-resume — 满足当前单人微信管家与 T6 |
| **不做（否决）** | LangGraph / SQLite Checkpointer 进 core、workflow 无门控自动续跑 — 见 [`roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §1 |
| **可选 Backlog** | 长 DAG 重跑成本高时：续跑读取 `checkpoint.json` / 修好 `pause_state.completed_steps` 并 **跳过已完成节点** — **纯工程**，不改 MA/MT |

配置速查：`BUTLER_WORKFLOW_CHECKPOINT`、`BUTLER_WORKFLOW_RUN_SNAPSHOT`、`BUTLER_WORKFLOW_AUTO_RESUME` — [`config/reference.md`](../config/reference.md)。

### 7.5 续跑矩阵（AP-11）

| 场景 | 默认 | `BUTLER_WORKFLOW_AUTO_RESUME=1` | checkpoint 读回（AP-14 未做） |
|------|------|-----------------------------------|------------------------------|
| workflow 步骤待 Owner 确认 | 阻塞子 Agent；再发 `/workflow` | 确认后自动 `run_workflow_for_project` | 不适用 |
| 已完成无门控步骤 | 重跑 `/workflow` **再执行** | 同上 | 未来可跳过已完成节点 |
| 入站普通聊天 | **不**因 workflow pending 阻塞 LLM | 同左 | — |
| Injection 待审 | 入站 guard 拦截；无 LLM | 同左 | — |

斜杠命令路径 **不** 调用 `AgentLoop.run`（见 `tests/gateway/test_hitl_zero_llm.py`）。

---

## 8. 理论边界

- 本文档 **不** 主张合并门控实现或放宽默认。
- 登记册 **G4**：未经前提测试的默认变更（如 prod 下放开 bypass）视为理论风险。
- Lead 工具隔离：见 [`project-activation.md`](project-activation.md) §4。

---

## 9. 审批存储矩阵（2026-07 收敛目标）

| 场景 | 存储 | 契约 | 微信命令 |
|------|------|------|----------|
| 通用 tool ask | `sessions/<sk>/approvals.json` | `ApprovalStore` | `/批准一次` `/始终允许` |
| Terminal exec | `sessions/<sk>/approvals.json` | `ApprovalStore` | `/批准执行` |
| Terminal pattern | `sessions/<sk>/terminal_patterns.json` | session 文件 | smart-approve |
| Workflow 步骤 | `human_gates/*.json` | `WorkflowGateStore`（`human_gate` 实现） | `/确认` |
| MCP mutating | `approvals.json` | `ApprovalRequest` | 同 tool ask |

统一 pipeline 入口：`butler/core/tool_orchestrator.py` — `run_tool_with_policy_gates` / `run_terminal_with_gates` / `run_mcp_with_gates`。

---

## 10. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | Phase C4 初稿 |
| 2026-06-11 | §7：人工门控 vs workflow/compaction 三类「检查点」语义 |
| 2026-07-07 | §9：审批存储矩阵 + ApprovalStore / terminal 迁入 approvals |
| 2026-07-07 | §9：Terminal exec/pattern 统一 `sessions/<sk>/`；遗留 `exec_approvals` 只读迁移 |
