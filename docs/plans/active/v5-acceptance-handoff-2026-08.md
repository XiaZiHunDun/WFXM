# Butler v5 开发收口 → 验收交接（2026-08-21）

> **状态**：Accepted — 2026-08-21 验收通过（`pnpm test:p4-acceptance` + 全量 762 tests + verify/healthz）  
> **上一班结论**：P4 MVP 链 + 真实路径 harness + 交付面加固已完成；开发主线收口  
> **工程规约**：[`../decisions/v5-engineering-handoff-2026-08.md`](../decisions/v5-engineering-handoff-2026-08.md)  
> **产品边界**：[`../decisions/v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md)  
> **生产事实**：[`../../architecture/v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md) §6.0–§6.0f  
> **架构对齐长文**：[`v5-architecture-alignment-handoff-2026-08.md`](v5-architecture-alignment-handoff-2026-08.md)（背景用；本验收会话以本文为准）

---

## 1. 下一会话目标

做 **验收与冒烟**，确认已交付面可用。默认**不立项、不实现**新能力。

成功标准：

1. `cd butler-v5 && pnpm test:p4-acceptance` 绿  
2. （可选）`cd butler-v5 && pnpm test` 全绿  
3. （可选）真库 / 真进程：`butler verify [--api …]` + 手工 Owner/微信路径对照下文清单打勾  

若验收发现缺陷：优先**修已交付面的 bug**；不要顺手开 Project Knowledge / UI / 浏览器。

---

## 2. 开篇 30 秒

1. 读 [`.blackboard/state.md`](../../../.blackboard/state.md)  
2. 读**本文**（验收范围与清单）  
3. 需要路径细节时再读 production architecture §6.0–§6.0f  
4. 不要从 `docs/history/` 或 v4 推断 v5  

---

## 3. 本轮已交付（验收对象）

| 能力 | 关键开关 / 入口 | 备注 |
| --- | --- | --- |
| Schedule / Heartbeat | `BUTLER_V5_SCHEDULE_ENABLED`（默认关） | `source=schedule`；只读工具白名单 |
| Durable Memory | `BUTLER_V5_DURABLE_MEMORY=1` 才注入 Loop | Owner/CLI + `recall_durable_memory` |
| Document ingest | Owner/CLI `butler document …` | pdf **必须**预提取文本；无 OCR |
| Local tracing | 默认开；`BUTLER_V5_TRACE=0` 关 | `butler traces`；可选 `BUTLER_V5_OTEL_EXPORTER=stdout` |
| Task / Procedure | Owner/CLI `butler task …` | `source=task`；线性模板；无 DAG |
| P4 harness | `pnpm test:p4-acceptance` | **模拟** `POST /v1/wechat/inbound`，无真 iLink |
| 迁移 | `0004`–`0006`；`butler verify` | 打开 DB 时自动 `applyMigrations` |

**明确不在本轮**：Web UI、Playwright/浏览器、RAG Studio、完整 OTEL SDK、DAG/WorkflowRun、压缩摘要自动升记忆。

---

## 4. 推荐验收步骤（按顺序）

### A. 自动化（必做）

```bash
cd butler-v5
pnpm test:p4-acceptance
# 覆盖：模拟微信 inbound → Schedule fire → Task/Procedure 推进 → Owner traces
# 另含：迁移清单 0004–0006、trace 脱敏单测

butler verify
# 期望打印 migrations ok（含 0004–0006）
```

可选全量：

```bash
cd butler-v5 && pnpm test
```

上一开发班次末次全量：**150 files / 762 tests** 通过（以你跑的结果为准）。

### B. 真进程冒烟（建议，需本地 API）

1. 起 API（按你现有方式，如 `butler start`；Owner CLI 默认连 `http://127.0.0.1:3000`）  
2. `butler verify --api http://127.0.0.1:3000`  
3. 对照：

| 检查 | 命令 / 动作 | 期望 |
| --- | --- | --- |
| 健康 | `GET /healthz` 或 verify | 200 / ok |
| Task | `butler task proc-add '…'` → `add` → `run` → `list` | 步骤可推进；Run `triggerSource=task` |
| Traces | `butler traces` 或 Owner `GET /v1/owner/traces` | 有 run start/finish；脱敏开启时无明文 Bearer/JWT |
| Schedule | 仅当显式 `BUTLER_V5_SCHEDULE_ENABLED=1` | 默认关；打开后 tick 不抢 busy 主 Run |
| Memory/Document | CLI add/list/recall 工具路径 | 表存在；inject 默认仍关 |

### C. 真微信（可选，Owner 自控）

- 仅当你准备好 iLink / token；**不要**把真 iLink 绑进日常 `pnpm test`  
- 手工发一句「只读巡检」类消息，确认入站走 `/v1/wechat/inbound` 同源 Loop  
- 审批类路径：微信短句确认仍可用；与本轮 P4 无强绑定  

Harness 已覆盖「模拟微信 HTTP」；真微信是环境验收，不是功能回归门禁。

---

## 5. 关键文件速查

| 用途 | 路径 |
| --- | --- |
| 验收 harness | `butler-v5/apps/api/src/p4-acceptance.harness.test.ts` |
| 冒烟脚本 | `butler-v5/scripts/p4-acceptance.sh` → `pnpm test:p4-acceptance` |
| Task 执行 | `butler-v5/apps/api/src/task-run.ts` |
| Schedule 执行 | `butler-v5/apps/api/src/schedule-run.ts` |
| 微信入站 HTTP | `butler-v5/apps/api/src/routes.ts` → `runButlerLoop` |
| 迁移清单 | `butler-v5/packages/persistence/src/migrations/run-migrations.ts` |
| Trace 脱敏 | `butler-v5/packages/domain/src/observability/local-trace.ts` |
| Owner 路由 | `butler-v5/apps/api/src/owner-routes.ts` |
| CLI | `butler-v5/cli/src/index.ts`（`task` / `traces` / `verify` / `document` / `memory`） |

---

## 6. 已知边界（验收勿当 bug）

- Schedule / Durable Memory 注入：**默认关**（opt-in）  
- Procedure `when`：**仅标签**，不求值  
- PDF：必须预提取文本，无内嵌解析器  
- Trace：本地环形缓冲；stdout OTEL 不是完整 SDK  
- `butler verify` 不跑 harness；验收自动化以 `pnpm test:p4-acceptance` 为准  

---

## 7. 验收后怎么收

- **全绿**：把 `.blackboard/state.md` 标成「验收通过」；可关闭本文 Active 或改 status 为 Accepted  
- **有缺陷**：在 state 写清失败命令与现象；修 bug 后复跑 A；仍**不要**开新 P4 产品面  
- **按需新能力**（如 Project Knowledge）：另开会话 + Owner 立项，不在本验收会话做  

---

## 8. 上一班一句话

开发已收口；下一班只验收：`pnpm test:p4-acceptance` →（可选）真进程/`butler verify` →（可选）真微信。
