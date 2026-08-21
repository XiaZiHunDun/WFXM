# @butler/infrastructure — 已归档 / 保留模块

| 模块 | 路径 | 状态 |
|------|------|------|
| `guards` | `_archive/guards/` | 已归档 |
| `acl` | `_archive/acl/` | 已归档 |
| `shadow` | `_archive/shadow/` | 已归档 |
| `persistence` (Drizzle 并行 schema) | `_archive/persistence/` | 已归档；生产用 `packages/persistence` |
| `mcp` (Effect stub) | `_archive/mcp/` | 已归档；生产 MCP 在 `apps/api/mcp-bootstrap.ts` |
| `patch` | `_archive/patch/` | 已归档 |
| `llm` / `wechat` | `_archive/llm/` `_archive/wechat/` | 已归档 |
| `migration/v4-to-v5` | `src/migration/` | **保留**至 D1 后评估 |

`layers.ts` 仍从 `_archive` 引用 stub Layer，仅供 Effect 示例；**禁止** `apps/*` 导入。
