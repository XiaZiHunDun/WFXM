# Butler MCP 能力（P3）

> **状态**：已落地（2026-05）  
> **安装**：`pip install butler-system[mcp]`  
> **默认**：`BUTLER_MCP_ENABLED=0`（关闭）

## 能力范围

| 做 | 不做 |
|----|------|
| 薄 MCP Client（stdio + HTTP/SSE） | OpenCode 级 MCP Host（npm 市场、OAuth 浏览器） |
| 工具名 `mcp_{server}_{tool}` 注入 Loop | 动态安装 MCP Server |
| 项目 `tools` 白名单 + `mcp_*` 通配 | 委派子 Agent 默认禁用 MCP |
| `butler mcp serve` 暴露只读工具 | 微信主路径依赖 MCP |

## 配置

全局：`~/.butler/mcp.yaml` 或 `BUTLER_MCP_CONFIG`。项目可覆盖：`<workspace>/.butler/mcp.yaml`。

**合并规则**：project → `BUTLER_MCP_CONFIG` → global；同名 `server_id` **后层覆盖**。路径 SSOT：[`extension-registry-paths.md`](../../architecture/extension-registry-paths.md) §3。

**SSOT 快照**（只读索引 / 安装审计，非第二份配置）：

| 文件 | 路径 | CLI |
|------|------|-----|
| `mcp.lock.json` | `~/.butler/mcp.lock.json` | `butler mcp add` 成功后自动更新 |
| `mcp-ssot.yaml` | 项目 `.butler/` 或 `~/.butler/` | `butler mcp sync [--workspace PATH] [--reload]` |

运维契约（结构示例、`BUTLER_TOOLS_ENGINE_SSOT`）：[`execution-surface-design.md`](../../architecture/execution-surface-design.md) §4.6。

示例见仓库根目录 [`.butler/mcp.yaml.example`](../../../.butler/mcp.yaml.example)。

## 环境变量

见 [`docs/config/reference.md`](../../config/reference.md) 中 `BUTLER_MCP_*` 表。

## 权限

`project.yaml` 的 `tools` 须包含具体 `mcp_*` 工具名或 `mcp_*` 通配。

`permissions.yaml` 可对 MCP 工具设 last-match 规则，例如：

```yaml
rules:
  - tool: "mcp_*"
    action: ask
    reason: "MCP 调用需 Owner 确认"
```

## CLI

```bash
butler mcp serve                    # stdio Server，供 Cursor 连接 Butler 只读工具
butler mcp add <id> [--project]     # 安装 + probe → mcp.yaml + mcp.lock.json
butler mcp sync [--workspace PATH]  # 刷新 mcp-ssot.yaml（合并视图）
butler mcp status                   # 配置层 + 生效 server
butler mcp reload                   # 断开连接，下轮重读 yaml
```

## 模块

| 路径 | 说明 |
|------|------|
| `butler/mcp/config.py` | 配置加载与校验 |
| `butler/mcp/manager.py` | 连接池（按 session 或进程） |
| `butler/mcp/registry_hook.py` | 挂接 `tools/registry` |
| `butler/mcp/server_stdio.py` | 对外 MCP Server |
