# 项目激活与运行时影响（Phase C2）

> **状态**：2026-06-09  
> **用途**：回答「激活/切换项目后，哪些字段影响 Loop、工具、观测」；**不**替代 [`layered-model-config.md`](layered-model-config.md)（模型 L0–L3）。  
> **关联**：[`project/meta.py`](../../butler/project/meta.py) · [`project/lead.py`](../../butler/project/lead.py) · [`tools/project_tools.py`](../../butler/tools/project_tools.py)

---

## 1. 激活是什么意思

**会话绑定项目** = `ProjectManager` 为 `session_key` 记住当前 `project.yaml` 对应工作区。  
入口：微信 `/切换 <名>`、`/项目`、部分命令隐式解析。

**默认项目**（无会话绑定时）：

| 来源 | 变量/字段 | 优先级 |
|------|-----------|--------|
| 环境 | `BUTLER_DEFAULT_PROJECT` | 新会话兜底 |
| 会话 | 已绑定项目名 | **高于** env 默认 |

`/诊断` 会输出「默认项目策略」块（`format_default_project_policy_lines`）。

---

## 2. 项目字段 → 运行时影响

| `project.yaml` / 元数据 | 影响面 | 模块 |
|-------------------------|--------|------|
| `workspace` | 工具 cwd、MEMORY.md、`.butler/*`、MCP 项目层 | `project_tools`, `mcp/config` |
| `models.*` | 四角色 **L2** 覆盖（`resolve_effective_model`） | `model_resolve.py` |
| `tools` / `tool_modes` | 工具白名单、Lead 只读子集、plan 模式 | `tools/project_tools.py` |
| `lead` + `pack` | 网关主线程用 **Lead** 还是 **Butler** Loop | `project/lead.py` |
| `tenant` | 全局记忆/技能租户目录 | `tenant.py` |
| `permissions` → `.butler/permissions.yaml` | 声明式工具权限、workflow 步骤白名单 | `permissions/rules.py` |
| `workflows` | DAG / handoff（非本页详述） | `workflows/` |
| `lifecycle` / `pack` | Lead 系统提示运营态（维护 vs 活跃创作） | `project/meta.py` |
| `langfuse.json`（`~/.butler/projects/<id>/`） | 可选 per-project LangFuse 凭证 | `ops/langfuse_tracer.py` |

---

## 3. Lead（厂长）判定

`is_lead_project()` 为真时，`gateway_loop_role()` → `"lead"`（否则 `"butler"`）。

判定顺序（`butler/project/lead.py`）：

1. `project.lead: false` → **否**（显式关闭）
2. `project.lead: true` → **是**
3. 项目名 ∈ `BUTLER_LEAD_PROJECTS`（默认含 `灵文1号` / `灵文1`）
4. `pack: novel-factory` → **是**（除非已被 `lead: false` 否决）

**模型层**：角色名 `lead` 在 `model_resolve` 中 **别名到 `butler`**（L2 仍读 `models.butler`）。  
**画像层**：`agent_profiles.py` 的 `lead_agent` / `LEAD_AGENT` 用于 **委派子 agent 提示**，与网关主线程角色不同。

`/状态`、`/诊断` 会显示「对话引擎: 项目 Lead」或「管家 Butler」。

---

## 4. 工具与画像

### 4.1 `project.tools` 与 `tool_modes`

- 未配置 `tools` → 工具集不受项目列表限制（仍受全局权限/门控）。
- 配置 `tools` → 映射到 registry 名（`canonical_tool_name`）。
- `tool_modes.<role>` → 在该角色下进一步收窄；**Lead** 模式强制只读工具集 + 少量委派工具（`project_tools._LEAD_READ_TOOLS`）。

### 4.2 `agent_profiles`

- 路径：`butler/agent_profiles.py`
- 用途：`delegate_task` 子 agent 的系统提示片段（dev/content/review/**lead_agent**）
- **不**直接决定网关主 Loop 角色（那是 `gateway_loop_role`）

---

## 5. 租户与 LangFuse

### 5.1 Tenant

- 解析：`resolve_tenant_for_project(project, settings)`  
  顺序：`project.tenant` → `config.yaml default_tenant` → `default`
- 路径：`~/.butler/tenants/<tenant>/memory`、`.../skills`
- 与项目 workspace 下 `.butler/` **并存**（项目记忆 vs 租户全局记忆）

### 5.2 LangFuse

- 全局：`BUTLER_LANGFUSE_ENABLED` + `LANGFUSE_*` env
- 项目：`~/.butler/projects/<project_id>/langfuse.json`（`config.load_project_langfuse_config`）  
  启用时 tracer 可为该项目单独建 client

---

## 6. 排障速查

| 现象 | 先查 |
|------|------|
| 切换项目后模型没变 | `/模型` 或 `/诊断` 有效模型行；确认 `project.models.*` |
| 进了厂长模式 | `/诊断` 项目元数据「厂长 Lead」；`lead` / `pack` / `BUTLER_LEAD_PROJECTS` |
| 工具找不到 | `project.tools` / `tool_modes`；`permissions.yaml` |
| MCP 少 server | 项目 `<workspace>/.butler/mcp.yaml` 是否覆盖全局（见 [extension-registry-paths.md](extension-registry-paths.md)） |

---

## 7. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | Phase C2 初稿 |
