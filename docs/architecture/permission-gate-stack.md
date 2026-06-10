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

## 7. 理论边界

- 本文档 **不** 主张合并门控实现或放宽默认。
- 登记册 **G4**：未经前提测试的默认变更（如 prod 下放开 bypass）视为理论风险。
- Lead 工具隔离：见 [`project-activation.md`](project-activation.md) §4。

---

## 8. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | Phase C4 初稿 |
