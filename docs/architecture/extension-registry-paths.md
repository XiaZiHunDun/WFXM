# 扩展注册路径优先级（Phase C3）

> **状态**：2026-06-09  
> **用途**：Hook / MCP / Skill 配置「放哪、谁覆盖谁」；仿 L0–L3 写法，**只描述路径**。  
> **关联**：[`hooks/loader.py`](../../butler/hooks/loader.py) · [`mcp/config.py`](../../butler/mcp/config.py) · [`registry/mcp_merge.py`](../../butler/registry/mcp_merge.py) · [`orchestrator/`](../../butler/orchestrator/__init__.py)（原 `orchestrator.py` 已重构为包）

---

## 1. 总览

| 扩展 | 全局（管家） | 项目层 | 合并规则 |
|------|--------------|--------|----------|
| **Hooks** | `config.yaml` `hooks:` + `~/.butler/.butler/hooks.yaml` | `<workspace>/.butler/hooks.yaml` | 列表 **追加**（先全局后项目） |
| **MCP** | `~/.butler/mcp.yaml`（或 `BUTLER_MCP_CONFIG`） | `<workspace>/.butler/mcp.yaml` | 同 `server_id` **后层覆盖** |
| **Skills** | `~/.butler/tenants/<tenant>/skills/*.md` | `<workspace>/.butler/skills/*.md` | **同名项目文件覆盖**租户全局 |
| **Skill Registry** | Hub 目录 `~/.butler/tenants/<tenant>/skills/.hub` | 安装目标可选 project/global | 见 `butler registry` CLI |

---

## 2. Hooks

**加载**：`hooks/loader.py` → `load_hooks_config(workspace)`

顺序：

1. `~/.butler/config.yaml` 内 `hooks:` 段（若存在）
2. `~/.butler/.butler/hooks.yaml`
3. `<workspace>/.butler/hooks.yaml`（有激活项目时）

事件类型：`PreToolUse`、`PostToolUse`、`SessionStart`、`Stop`、`SubagentStop` 等（见模块内 `_HOOK_EVENTS`）。

示例模板：[`hooks/hooks.yaml.example`](../../butler/hooks/hooks.yaml.example)

**注意**：`butler/gateway/hooks.py` 为 Python 低延迟注入，**不走** hooks.yaml。

---

## 3. MCP

### 3.1 读取顺序（effective）

`mcp/config._resolve_config_paths(workspace)` → `load_mcp_servers()`：

1. `<workspace>/.butler/mcp.yaml`（或 `.yml`）
2. `BUTLER_MCP_CONFIG` 指向的文件（若设置）
3. `~/.butler/mcp.yaml` / `mcp.yml`

同一 `server_id`：**后出现的文件覆盖先出现的**（`effective_mcp_servers` 注释：project → env path → global）。

### 3.2 写入目标

| 操作 | 默认路径 |
|------|----------|
| `butler mcp add`（全局） | `~/.butler/mcp.yaml` |
| `butler mcp add --workspace` / 微信 `/mcp 安装`（有项目） | `<workspace>/.butler/mcp.yaml` |
| env 覆盖全局路径 | `BUTLER_MCP_CONFIG` |

诊断：`format_mcp_merge_diagnostic_lines`（`/诊断` RAG/MCP 块）、`mcp registry_hook` 连接状态。

损坏的 yaml：层内解析失败会记入 `recent_mcp_merge_corruptions()`，**不阻塞**其他层。

### 3.3 SSOT 快照（非运行时配置）

| 文件 | 路径 | 说明 |
|------|------|------|
| `mcp.lock.json` | `~/.butler/mcp.lock.json` | `butler mcp add` probe 成功后写入；安装审计 |
| `mcp-ssot.yaml` | `<workspace>/.butler/mcp-ssot.yaml` 或 `~/.butler/mcp-ssot.yaml` | `butler mcp sync` 生成的 **只读** 合并索引 |

详述与运维话术：[`execution-surface-design.md`](execution-surface-design.md) §4.6。

---

## 4. Skills

### 4.1 运行时 SkillManager

`orchestrator._combined_skill_manager()`：

| 目录 | 含义 |
|------|------|
| `~/.butler/tenants/<tenant>/skills/` | 租户全局技能 |
| `<workspace>/.butler/skills/` | 项目技能（**优先**同名） |

无激活项目时仅租户目录。

租户解析：`resolve_tenant_for_project`（`project.tenant` → `default_tenant` → `default`）。

### 4.2 仓库内 `skills/`（git）

小说工厂等可能在项目根 `skills/` 有内容；`project/preflight.py` 约定 **git `skills/` 优先于 `.butler/skills/`** 同名去重（与 SkillManager 路径不同，属内容同步层）。

### 4.3 Registry / Hub

- 开关：`BUTLER_SKILL_REGISTRY`（默认开）
- 源列表：`BUTLER_SKILL_REGISTRY_SOURCES`（bundled, project, github, …）
- Hub 根：`registry/paths.skills_root(tenant_id)` → `.../skills/.hub`
- CLI：`butler registry`、`butler skills`、微信 `/技能`

---

## 5. 与配置四分法的关系

| 面 | 扩展配置 |
|----|----------|
| C `config.yaml` | `hooks:` 段（可选） |
| C 独立 yaml | `mcp.yaml`、`hooks.yaml`（`.butler/` 下） |
| A env | `BUTLER_MCP_*`、`BUTLER_SKILL_REGISTRY*`、`BUTLER_MCP_CONFIG` |
| 项目 | `project.yaml` 不直接列 MCP；用 workspace 下 `.butler/` |

详见 [`config-surfaces.md`](../config/config-surfaces.md)。

---

## 6. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | Phase C3 初稿 |
