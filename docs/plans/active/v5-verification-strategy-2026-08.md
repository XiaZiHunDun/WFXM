# Butler v5 验收策略 — 少真机、多自动化（2026-08-25）

> **原则**：真机微信只做**连通性**与**不可替代**的点验；功能回归走 loopback + 单测 + 聚合 smoke。  
> **SSOT 命令**：`butler-v5/package.json` · `scripts/cutover/smoke-*.mjs`

---

## 1. 验证金字塔

| 层 | 做什么 | 何时跑 | 真机？ |
| --- | --- | --- | --- |
| **L0 门禁** | `pnpm test` · `pnpm test:p4-acceptance` · `tsx cli verify` | 每次改代码 / CI | 否 |
| **L1 Loopback 微信** | `POST /v1/wechat/inbound` 模拟入站，覆盖 slash 命令、PK、MCP 配置 | 合并前 / 部署后 | 否 |
| **L2 聚合回归** | `pnpm smoke:regression` · CI: `pnpm smoke:ci-regression` | 部署后 / PR·push | 否 |
| **L3 iLink 连通** | `pnpm smoke:ilink` — getupdates 探活；可选 `--send-ping` 发一条 | 换 token / 部署后 / 故障时 | **仅 1 次探活** |
| **L4 真机点验** | 肉眼确认消息能收能发、会话未过期 | 换 env / 重大 Channel 变更 | **最小集** |

**禁止**：为每个 slash 命令做真机全矩阵点验。

---

## 2. L1 子 smoke 与覆盖范围

| 脚本 | npm 别名 | 覆盖 |
| --- | --- | --- |
| `smoke-wechat-inbound-commands.mjs` | `smoke:wechat-commands` | `/记住` `/记忆` `/待办` `/完成` `/验` |
| `smoke-wechat-project-surface.mjs` | `smoke:project-surface` | `/项目` `/切换` `/状态` `/项目概况` `/项目 体检` |
| `smoke-wechat-productivity.mjs` | `smoke:productivity` | `/委派` `/委派状态` |
| `smoke-wechat-notify-acceptance.mjs` | `smoke:notify-acceptance` | 委派+待办异步 + **audit**（`--audit-only` 不依赖 mock outbox） |
| `smoke-project-knowledge.mjs` | _(direct)_ | PK inject/recall · wechat/LingWen1 映射 |
| `smoke-mcp-hardened.mjs` | `smoke:mcp` | MCP status/allowlist · Grant 或 readonly-auto |
| `smoke-durable-memory.mjs` | `smoke:durable-memory` | Durable Memory 路径 |
| `smoke-document-ingest.mjs` | `smoke:document-ingest` | Document ingest |

Loopback 与真机差异（已知、可接受）：

- 推送：L1 用 mock outbox 或 **audit-only**；L3/L4 验 iLink sendmessage。
- 附件/语音：单测 + ilink-media；真机仅故障时抽测。
- LLM 措辞：断言 **trace/工具链/关键词**，不断言逐字回复。

---

## 3. 推荐命令

```bash
cd butler-v5

# 日常（改代码后）
pnpm test

# 部署后 / 合并前（~5–15 分钟，含 LLM）
pnpm smoke:regression

# CI（gateway pglite + loopback，无 iLink / 无 LLM notify）
pnpm smoke:ci-regression

# 快速（跳过 PK + 全量 MCP grant，~2 分钟）
pnpm smoke:regression -- --quick

# iLink 探活（不打扰用户，默认只 getupdates）
pnpm smoke:ilink

# 可选：向指定用户发一条连通性消息（需 BUTLER_V5_ILINK_PING_TO）
pnpm smoke:ilink -- --send-ping

# 真机最小集（人工，<2 分钟）
# 1. 微信发「ping」或任意短句 → 有回复
# 2. （仅当刚换 token）pnpm smoke:ilink -- --send-ping
```

---

## 4. L4 真机最小清单（仅必要时）

| # | 操作 | 通过标准 |
| --- | --- | --- |
| 1 | 发任意短消息 | 数秒内收到管家回复 |
| 2 | `pnpm smoke:ilink` | getupdates 无 auth 错误 |
| 3 | （可选）`/切换 灵文1号` + 一问 | 回复体现灵文上下文（非每次发布必做） |

**不必**每次发布真机跑：/待办全链、MCP Grant、PK recall、/委派推送——已由 L1/L2 覆盖。

---

## 5. 推送验收分工

| 模式 | 用途 |
| --- | --- |
| `enable-subagent-prod.sh --mock-outbox` + `smoke:notify-acceptance` | Loopback 验证推送**逻辑**（写 JSONL） |
| `enable-subagent-prod.sh`（无 mock）+ `smoke:notify-acceptance --audit-only` | 验证 worker **完成**且不依赖 outbox |
| `smoke:ilink --send-ping` | 验证 iLink **出站**连通 |
| 真机收 `/委派` 完成通知 | 仅 major 发布或 ilink 变更后 |

---

## 6. CI 集成

| 工作流 | 步骤 |
| --- | --- |
| [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml) `butler-v5-gate` | `bash scripts/cutover/ci-smoke-regression.sh` |
| [`butler-v5/.github/workflows/ci.yml`](../../../butler-v5/.github/workflows/ci.yml) | job `smoke-regression` |

`ci-smoke-regression.sh`：pglite gateway + `smoke:regression --quick --skip=notify`（无 iLink token、无 LLM notify）。

---

## 7. 相关文档

- 工程交接：[`v5-engineering-handoff-2026-08.md`](../decisions/v5-engineering-handoff-2026-08.md)
- PK 交接：[`v5-project-knowledge-handoff-2026-08.md`](v5-project-knowledge-handoff-2026-08.md)
- MCP 交接：[`v5-mcp-multi-server-handoff-2026-08.md`](v5-mcp-multi-server-handoff-2026-08.md)
