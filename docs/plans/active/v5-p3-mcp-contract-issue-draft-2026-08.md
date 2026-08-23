# GitHub Issue 草稿 — P3 MCP 注册契约补全

> **状态**：Done — [GitHub #3](https://github.com/XiaZiHunDun/WFXM/issues/3)（2026-08-23）  
> **路线图**：[`v5-post-boundary-roadmap-2026-08.md`](v5-post-boundary-roadmap-2026-08.md) §P3.3  
> **架构差距**：[`v5-architecture-alignment-handoff-2026-08.md`](v5-architecture-alignment-handoff-2026-08.md) §5.9

---

## 背景

P3 MCP 首个适配 **部分交付**：manifest gate、consent、transport、extraProviders 已在生产路径。以下三项仍属 **P3 余量**，不应在 P4 验收会话顺手实现。

## 目标（立项后）

1. **per-tool ScopedGrant** — MCP 工具调用可绑定 Grant（capability + server/tool scope），Child Run 默认无 MCP。
2. **Provider 卸载 Grant 失效** — 卸载 MCP server 后，关联 Grant 自动 revoke（fail-closed）。
3. **risk / sandbox / audit 声明骨架** — Provider 注册表声明默认 risk class、sandbox profile、audit policy；与 P2 Grant profile 对齐。

## 不在范围

- MCP Marketplace 自动安装
- 远程 OAuth token passthrough
- 浏览器 / Playwright
- 第二套 Run Engine 或 Policy

## 主要触点（预估）

| 区域 | 路径 |
| --- | --- |
| MCP bootstrap | `butler-v5/apps/api/src/mcp-bootstrap.ts` |
| Manifest / consent | `mcp-manifest.ts`, `packages/runtime/src/mcp-consent.ts` |
| Grant 签发 | `packages/runtime/src/approval-runtime.ts` |
| Policy / boundary | `packages/runtime/src/policy-gate.ts`, `capability-boundary.ts` |
| 审计 | `packages/persistence` audit / Step 元数据 |

## 验收（草案）

- [x] 未 Grant 的 MCP 工具在 Policy 层 Deny/Ask（`isMcpCapability` → alwaysConfirm）
- [x] Grant 绑定 server + tool（`ScopedGrantScope.mcp` + `grantMatchesAction`）
- [x] Owner 卸载/禁用 MCP server 后 revoke grants（`bootstrapMcpTools` + `revokeScopedGrantsForMcpServer`）
- [x] Provider 元数据骨架（`defaultMcpProviderMetadata`：risk/sandbox/audit）
- [x] Owner API/CLI 手动 revoke（`GET /v1/owner/mcp/status`、`POST .../revoke-grants`、`butler mcp`）
- [x] MCP 执行 trace 含 provider 元数据 + Grant mcp scope

## 顺序约束

- P1/P2 已交付 — 可立项
- 不得引入第三套扩展接缝
- 修改 AI 守卫承重文件需 `[MANUAL-OVERRIDE]`

## 建议第一步

1. 在 domain 层定义 `McpToolCapability` + Grant scope 规范化（纯函数 + 单测）
2. `policy-gate` 对 `mcp_*` 工具校验 Grant scope
3. `mcp-bootstrap` 卸载 hook → revoke grants by server id

---

**Owner 动作**：确认立项后 `gh issue create`，标题建议：`feat(v5): P3 MCP per-tool Grant and provider unload revoke`
