# Butler v5 MCP 多 Server 生产接线 — 会话交接（2026-08-23）

> **状态**：Hardened — github 只读裁剪 + 微信 allowlist + Grant smoke（2026-08-25）  
> **上一 commit（multi bootstrap）**：`6c8d2ced`（2026-08-23）  
> **加固**：`b59651a2`（github trim + allowlist）；验收 `pnpm smoke:mcp`  
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

### 生产 MCP 现状（2026-08-25）

```
mode: multi
servers: markitdown(1) + firecrawl(3) + github(14 read-only) + todoist(4) = 22 tools
wechat allowlist: BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH=config/wechat-tool-allowlist.json
activeGrants: 0（常态；MCP 调用走 Ask → Owner approve → 单次 Grant）
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
| **微信 MCP 白名单** | `butler-v5/config/wechat-tool-allowlist.json` |
| **启用脚本** | `butler-v5/scripts/cutover/enable-mcp-prod.sh` |
| **Smoke** | `butler-v5/scripts/cutover/smoke-mcp-hardened.mjs` |
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
| github | `butler-v5/node_modules/.bin/mcp-server-github` | manifest `tools` 只读 14 项（search/get/list） |
| todoist | `node_modules/.bin/openapi-mcp-server` + openapi spec | lst/get 只读 4 工具 |

markitdown 用 `uv tool install markitdown-mcp` 预装；其余三者在 workspace `pnpm add -wD`。**勿用 npx 冷启动**（bootstrap 超时/并行失败）。

---

## 6. 推荐下一班步骤（按优先级）

### A. 日常回归（必做）

```bash
cd butler-v5 && pnpm test
pnpm smoke:mcp                    # config + grant path（外部 API 502 时 grant 仍绿）
pnpm smoke:mcp -- --skip-grant    # 仅 manifest/allowlist/status
pnpm exec tsx cli/src/index.ts mcp status --api http://127.0.0.1:3000
```

生产 env 幂等启用：`scripts/cutover/enable-mcp-prod.sh`

### B. 真调用验收（Owner 点验）

1. 微信触发 Todoist / Firecrawl 等 MCP 任务  
2. 回复「确认」或 Owner API approve → 查 `grant.scope.mcp`  
3. Todoist 502 时查 `~/.config/butler-v5/env` 中 `TODOIST_API_TOKEN` / `API_HEADERS`  
4. `butler traces` 或 Owner traces API  

### C. 可选产品向

| 选项 | 说明 |
| --- | --- |
| **Project Knowledge** | 需 Owner 单独立项 |
| **按 project 缩 MCP 子集** | 编辑 `config/wechat-tool-allowlist.json` |
| **github 再裁剪** | 编辑 manifest `github.tools` |
| **MCP 出网 allowlist** | approve 时传 `networkAllowlist`（Firecrawl 等） |

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

MCP hardened：github 14 只读工具、微信 allowlist 生产启用、`pnpm smoke:mcp` Grant 路径验收。
