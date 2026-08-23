# Butler v5 MCP 多 Server 生产接线 — 会话交接（2026-08-23）

> **状态**：Accepted — commit `6c8d2ced`（2026-08-23）  
> **上一班结论**：P3 MCP 契约 + 四 server 生产接线（markitdown / firecrawl / github / todoist）  
> **工程规约**：[`../decisions/v5-engineering-handoff-2026-08.md`](../decisions/v5-engineering-handoff-2026-08.md)  
> **P3 契约背景**：[`v5-p3-mcp-contract-issue-draft-2026-08.md`](v5-p3-mcp-contract-issue-draft-2026-08.md)（GitHub #3 Done）  
> **生产事实**：[`../../architecture/v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)

---

## 1. 下一会话开篇 30 秒

1. 读 [`.blackboard/state.md`](../../../.blackboard/state.md)  
2. 读**本文**（MCP 多 server 现状与后续选项）  
3. 改 MCP / Grant / bootstrap 时读 `butler-v5/apps/api/src/mcp-bootstrap.ts` + `config/mcp-manifest.json`  
4. 不要从 v4 `~/.butler/mcp.yaml` 或 `docs/history/` 推断 v5 实现  

---

## 2. 本班已交付

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| P3 MCP Grant + Owner API/CLI | ✅ | `6635d894` 已在 main |
| 稳态运维回归 | ✅ | test + smoke + verify 全绿 |
| MCP stub → 真实 server | ✅ | 先 markitdown，后四 server multi |
| **Multi-server bootstrap** | ✅ | manifest 驱动，并行 discover |
| **Capability 命名** | ✅ | 多 server 时 `mcp_{serverId}_{toolName}` |
| **Grant serverId 路由** | ✅ | approval / tool-boundary 按 capability 解析 |
| 生产 env + gateway | ✅ | `butler-v5-gateway.service` 已重启验收 |

### 生产 MCP 现状（2026-08-23 18:12）

```
mode: multi
servers: markitdown(1) + firecrawl(3) + github(26) + todoist(4) = 34 tools
activeGrants: 0（预期；调用仍走 Ask/审批）
```

验收命令：

```bash
cd butler-v5
pnpm exec tsx cli/src/index.ts mcp status --api http://127.0.0.1:3000
pnpm exec tsx cli/src/index.ts verify --api http://127.0.0.1:3000
```

---

## 3. 关键文件

| 用途 | 路径 |
| --- | --- |
| Multi bootstrap | `butler-v5/apps/api/src/mcp-bootstrap.ts` |
| Manifest 加载 | `butler-v5/apps/api/src/mcp-manifest.ts` |
| 连接解析（manifest 优先） | `butler-v5/apps/api/src/mcp-config.ts` |
| Capability 命名 / 解析 | `butler-v5/packages/domain/src/governance/mcp-tool-capability.ts` |
| Consent + serverId 解析 | `butler-v5/packages/runtime/src/mcp-consent.ts` |
| Owner status（多 server） | `butler-v5/apps/api/src/owner-routes.ts` → `GET /v1/owner/mcp/status` |
| **生产 manifest** | `butler-v5/config/mcp-manifest.json` |
| MCP npm 包（workspace） | `butler-v5/package.json` devDeps：`firecrawl-mcp`, `@modelcontextprotocol/server-github`, `@ivotoby/openapi-mcp-server` |
| 黑板快照 | `.blackboard/state.md` |

---

## 4. 生产 env（`~/.config/butler-v5/env`，不在 git）

```bash
BUTLER_V5_MCP_ENABLED=1
BUTLER_V5_MCP_MANIFEST_PATH=config/mcp-manifest.json
BUTLER_V5_MCP_TIMEOUT_MS=120000
BUTLER_V5_MCP_REQUIRE_CONSENT=1
BUTLER_V5_MCP_CONSENT=markitdown,firecrawl,github,todoist
# 密钥（勿提交）：
# FIRECRAWL_API_KEY=...
# GITHUB_PERSONAL_ACCESS_TOKEN=...
# TODOIST_API_TOKEN=...
# API_HEADERS="Authorization:Bearer ..."   # todoist stdio；必须加引号
```

**不要**在生产 env 留 `BUTLER_V5_MCP_COMMAND` / `BUTLER_V5_MCP_SERVER_ID`（会覆盖 manifest，曾导致 github 串到 markitdown）。

重启 gateway：

```bash
systemctl --user restart butler-v5-gateway.service
```

---

## 5. manifest 四 server 摘要

| id | command | 工具过滤 |
| --- | --- | --- |
| markitdown | `/home/ailearn/.local/bin/markitdown-mcp` | `convert_to_markdown` |
| firecrawl | `butler-v5/node_modules/.bin/firecrawl-mcp` | scrape/crawl/map only |
| github | `butler-v5/node_modules/.bin/mcp-server-github` | 全量 discover（26） |
| todoist | `node_modules/.bin/openapi-mcp-server` + openapi spec | lst/get 只读 4 工具 |

markitdown 用 `uv tool install markitdown-mcp` 预装；其余三者在 workspace `pnpm add -wD`。**勿用 npx 冷启动**（bootstrap 超时/并行失败）。

---

## 6. 推荐下一班步骤（按优先级）

### A. 提交后验证（必做）

```bash
cd butler-v5 && pnpm test
pnpm test:p4-acceptance
pnpm exec tsx cli/src/index.ts mcp status --api http://127.0.0.1:3000
```

### B. 真调用验收（建议）

1. 微信或 CLI 触发需 MCP 的任务（如「用 Firecrawl 抓 example.com」）  
2. Owner 审批 Grant → 确认 `activeGrants` 增加、`scope.mcp` 含正确 serverId/toolName  
3. 执行成功后查 trace：`butler traces` 或 Owner traces API  

### C. 可选产品向

| 选项 | 说明 |
| --- | --- |
| **Project Knowledge** | 需 Owner 单独立项，不在 P3/P4 MVP |
| **MCP 工具白名单** | 微信 Loop 侧按 project 过滤 34 工具中的子集 |
| **github 工具裁剪** | manifest `tools` 数组限只读工具，降低暴露面 |
| **读模型收敛** | `BUTLER_V5_READ_MODEL=relational` 已是默认，无需改 env |

### D. 明确不做

- 浏览器 / Playwright MCP  
- MCP Marketplace 自动安装  
- 修改 `scripts/ai_guard/*`（需 `[MANUAL-OVERRIDE]`）  

---

## 7. 已知问题 / 运维备注

1. **gateway 启动**：四 server 并行 bootstrap ~20s；本地 bin 路径依赖 workspace 绝对路径  
2. **firecrawl**：manifest 仅暴露 3 工具；discover 实际更多，已被 filter  
3. **github**：26 工具均为 high risk；Policy 默认 Ask  
4. **测试**：全量末次 749 passed；`workspace-tools.test.ts` 偶有环境 flaky  
5. **secrets**：`API_HEADERS` 必须 quoted，否则 `source env` 会断  

---

## 8. 日常回归命令

```bash
cd butler-v5 && pnpm test:p4-acceptance && pnpm test
pnpm smoke:allowlist-production
pnpm smoke:allowlist-slirp
pnpm smoke:allowlist-pnpm
pnpm smoke:schedule
pnpm exec tsx cli/src/index.ts verify --api http://127.0.0.1:3000
```

---

## 9. 上一班一句话

P3 MCP 已生产启用四 server（34 工具）；multi-bootstrap + manifest 已落地；下一班优先真调用 Grant 验收或 Project Knowledge 立项。
