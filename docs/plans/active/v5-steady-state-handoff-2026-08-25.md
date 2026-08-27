# Butler v5 稳态运维交接（2026-08-25）

> **状态**：Accepted — 验收金字塔 L0–L4 已闭环；无阻塞开发项  
> **上一班结论**：iLink 出站/Owner 身份已配；CI 回归 + 真机 `ping→pong` PASS  
> **工程规约**：[`../decisions/v5-engineering-handoff-2026-08.md`](../decisions/v5-engineering-handoff-2026-08.md)  
> **验收策略 SSOT**：[`v5-verification-strategy-2026-08.md`](v5-verification-strategy-2026-08.md)  
> **后续路线图**：[`v5-post-boundary-roadmap-2026-08.md`](v5-post-boundary-roadmap-2026-08.md)（按需立项，非默认待办）  
> **新会话开篇**：读 `.blackboard/state.md` → **本文** → 按 §5 选任务

---

## 1. 下一会话定位

**默认模式：稳态运维 + 按需立项**。不要假设有未完成的 P4 MVP 或验收阻塞。

| 可以做 | 需单独立项 |
| --- | --- |
| 修 bug、扩 PK sources、MCP 运维 | Web UI、Playwright 浏览器 |
| 跑 smoke / 部署后回归 | PK embedding / K2 / RAG Studio |
| post-boundary P0 工程收口（人工） | 真机全 slash 命令矩阵 |
| Schedule cron / 微信摘要等增强 | 删 `~/backup-butler-home-20260825.tgz` |

---

## 2. 本班已完成（勿重复）

### 2.1 验收与自动化

| 项 | 证据 |
| --- | --- |
| 验收金字塔 L0–L4 文档 | [`v5-verification-strategy-2026-08.md`](v5-verification-strategy-2026-08.md) |
| 聚合回归 | `pnpm smoke:regression` · `pnpm smoke:regression:quick` |
| CI 回归 | `pnpm smoke:ci-regression` · root + `butler-v5/.github/workflows/ci.yml` |
| iLink 探活脚本 | `pnpm smoke:ilink` · 可选 `--send-ping` |
| iLink sendmessage 格式修复 | `scripts/cutover/smoke-ilink-connectivity.mjs`（`msg.to_user_id` + `item_list`） |
| Ping 配置脚本 | `scripts/cutover/configure-ilink-ping.sh` |

### 2.2 生产配置（`~/.config/butler-v5/env`）

| 变量 | 状态 |
| --- | --- |
| `BUTLER_V5_ILINK_ENABLED=1` | 真 iLink（无 `RUN_NOTIFY_MOCK_OUTBOX`） |
| `WECHAT_TOKEN` / `WECHAT_BASE_URL` | 已配 |
| `BUTLER_V5_ILINK_PING_TO` | `o9cq805eXvV1P4FmXkllg1UfzrBs@im.wechat` |
| `BUTLER_OWNER_WECHAT_ID` | 同上（内联审批 + Owner 身份） |
| Subagent / RUN_NOTIFY / TASK_RUN_ASYNC / MCP / PK | 均已开启 |

### 2.3 真机验证（2026-08-25 22:53 CST）

| 检查 | 结果 |
| --- | --- |
| L3 `pnpm smoke:ilink -- --send-ping` | PASS（Owner 已收到探测消息） |
| L4 微信发 `ping` | user 14:53:19 → assistant 14:53:21（~1.3s） |
| 会话 ID | `c-wechat-o9cq805eXvV1P4FmXkllg1UfzrBs-im.wechat` |

### 2.4 同周期前序交付（背景，一般不必重做）

- P3 MCP 契约余量（manifest metadata、architecture test）
- PK 运营扩 sources（WFXM +5、LingWen +7 globs；sync 后 WFXM 29 / LingWen 22 条）
- MCP 运维：Todoist smoke、Firecrawl/GitHub allowlist
- `enable-subagent-prod.sh` 默认真 iLink，`--mock-outbox` 仅 loopback

---

## 3. 生产快照（交接时点）

```bash
systemctl --user is-active butler-v5-gateway.service   # active
curl -sf http://127.0.0.1:3000/healthz                 # {"status":"ok","wiring":"v5"}
```

| 组件 | 事实 |
| --- | --- |
| Gateway | `butler-v5-gateway.service`（user systemd），`EnvironmentFile=~/.config/butler-v5/env` |
| DB | `BUTLER_V5_DB=postgres`，Docker compose |
| iLink poller | 启动日志：`[ilink-poller] started … dmPolicy=open` |
| 数据目录 | `~/.config/butler-v5/`（含 `env`、`ilink-sync.json`、`audit/subagent.jsonl`） |
| v4 备份 | `~/backup-butler-home-20260825.tgz` — **勿删** |

---

## 4. 关键路径

| 用途 | 路径 |
| --- | --- |
| 黑板快照 | `.blackboard/state.md` |
| 验收策略 | `docs/plans/active/v5-verification-strategy-2026-08.md` |
| CI smoke | `butler-v5/scripts/cutover/ci-smoke-regression.sh` |
| iLink ping 配置 | `butler-v5/scripts/cutover/configure-ilink-ping.sh` |
| iLink 探活 | `butler-v5/scripts/cutover/smoke-ilink-connectivity.mjs` |
| 生产 Loop | `butler-v5/apps/api/src/wechat-inbound-butler.ts` |
| iLink 协议 | `butler-v5/packages/adapters/src/wechat/ilink-protocol.ts` |
| 出站推送 | `butler-v5/apps/api/src/wechat-run-notify.ts` |
| PK 交接 | `docs/plans/active/v5-project-knowledge-handoff-2026-08.md` |
| MCP 交接 | `docs/plans/active/v5-mcp-multi-server-handoff-2026-08.md` |

---

## 5. 推荐命令

```bash
cd butler-v5

# 改代码后
pnpm test

# 部署后（~2 分钟）
pnpm smoke:regression:quick

# 发版前（含 PK，~5–15 分钟）
pnpm smoke:regression

# CI 同款 loopback（无 iLink token）
pnpm smoke:ci-regression

# 换 token / 故障时
pnpm smoke:ilink
pnpm smoke:ilink -- --send-ping    # 需 BUTLER_V5_ILINK_PING_TO

# 重启 gateway（改 env 后）
systemctl --user restart butler-v5-gateway.service
```

---

## 6. 下一会话可选任务（按优先级）

### A. 运维（无代码）

1. 定期 `pnpm smoke:regression:quick` 或 CI 绿即可  
2. PK：按场景扩 `config/project-knowledge-sources.json` → sync  
3. MCP：新 server 走 manifest + consent（见 MCP handoff）

### B. 按需立项（见 post-boundary roadmap）

| 候选 | 说明 |
| --- | --- |
| Schedule 增强 | cron 表达式、微信推送摘要 |
| P0 工程收口 | v5 AI guard 迁移（**人工**）、文档 superseded |
| P3 契约正式化 | Trigger/Capability 接缝（骨架已有） |

### C. 真机（仅 major 发布或 Channel 变更）

- 发 `ping` 或有回复即可；**不必**全 slash 矩阵  
- 可选：`/切换 灵文1号` + 一问（验 PK 上下文）

---

## 7. 不要做

- 真机全命令矩阵点验（L1/L2 已覆盖）  
- PK K2 / embedding / RAG Studio  
- Web UI / Playwright 浏览器（Owner 已不立项）  
- 删 `~/backup-butler-home-20260825.tgz` 或 `~/.config/butler-v5/`  
- 用 `docs/history/` 或 v4 文档推断 v5 实现  
- 擅自改受保护文件（见根 `.cursorrules` / `butler-v5/AGENTS.md`）

---

## 8. 已知注意点

1. **conversation `subject` ≠ iLink `to_user_id`**：loopback smoke 用 `mcp-smoke-*` 等；真机推送用 `@im.wechat` 格式 id。  
2. **`sim-wx-realdevice-*`** 是 loopback 测试 id，不是真机 userId。  
3. **discover userId**：查 `GET /v1/owner/conversations?projectId=wechat` 中带 `@im.wechat` 的 `subject`；或 `configure-ilink-ping.sh` + 真机发消息后从 getupdates 解析 `from_user_id`。  
4. **改 `~/.config/butler-v5/env` 后**必须 `systemctl --user restart butler-v5-gateway.service`。

---

## 9. 新会话 30 秒

1. [`.blackboard/state.md`](../../../.blackboard/state.md)  
2. **本文**  
3. 做验收/运维 → [`v5-verification-strategy-2026-08.md`](v5-verification-strategy-2026-08.md)  
4. 做 PK → [`v5-project-knowledge-handoff-2026-08.md`](v5-project-knowledge-handoff-2026-08.md)  
5. 做 MCP → [`v5-mcp-multi-server-handoff-2026-08.md`](v5-mcp-multi-server-handoff-2026-08.md)  
6. 查调用链 → [`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)

---

## 10. 上一班一句话

验收金字塔 L0–L4 全绿；Owner 微信 id 已写入 env；gateway 重启后真机 `ping→pong` ~1.3s；进入稳态运维，后续按需立项。
