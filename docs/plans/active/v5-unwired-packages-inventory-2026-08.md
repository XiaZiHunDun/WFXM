# Butler v5 未接线包清单（2026-08）

> **状态**：Active  
> **用途**：记录不在生产调用链上的 v5 包与模块，避免文档/测试误称为已交付能力  
> **架构事实**：[`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)

---

## 生产路径（已接线）

```text
butler-v5/cli + apps/api
  → packages/runtime（RunEngine / PolicyGate / approval-runtime）
  → packages/adapters（LLM / WeChat / sandbox / MCP client 适配器）
  → packages/persistence（唯一 schema + RuntimeStore）
  → packages/domain（类型 / 策略 / 转换）
```

架构测试 [`butler-v5/tests/architecture/apps-layer-boundaries.test.ts`](../../butler-v5/tests/architecture/apps-layer-boundaries.test.ts) 禁止 `apps/*` 导入 `@butler/application` 与 `@butler/infrastructure`。

---

## `@butler/application` — Effect 用例脚手架

| 模块 | 路径 | 状态 | 建议处置 |
|------|------|------|----------|
| `runLoop` | `packages/application/src/run-loop/` | 仅包内测试 + Mock Layers | **保留至 Run 收敛**：生产 Loop 在 `runtime` + `wechat-inbound-butler` |
| `delegateTask` | `packages/application/src/delegate-task/` | Mock ProjectService | **归档候选**：生产委派在 `delegate-runtime.ts` |
| `runWorkflow` | `packages/application/src/run-workflow/` | OPT-1 并行 Channel stub | **冻结**：非产品 Workflow DAG |
| `dream` | `packages/application/src/dream/` | Mock MemoryService | **冻结**：百轮记忆未立项 |

**不要**：用 application 单测声称微信管家 / 审批 / Grant 已交付。

---

## `@butler/infrastructure` — Effect Layer 骨架

| 模块 | 路径 | 状态 | 建议处置 |
|------|------|------|----------|
| `ProductionLayer` / `TestLayer` | `packages/infrastructure/src/layers.ts` | 无生产消费者 | **保留参考**：MCP/WeChat Port 组合示例 |
| EventStore (Drizzle) | `packages/infrastructure/src/persistence/` | 与 `packages/persistence` **并行 schema** | **勿接生产**；迁移工具仅测试 |
| LLM stub | `packages/infrastructure/src/llm/` | 模拟延迟 | **归档候选** |
| WeChat stub | `packages/infrastructure/src/wechat/` | log-only | **归档候选**；生产用 `adapters/wechat` |
| MCPDiscoveryLive | `packages/infrastructure/src/mcp/` | 硬编码 local 工具列表 | **参考实现**；生产 MCP opt-in 在 `apps/api/mcp-tools.ts` |
| Guards G-1~G-7 | `packages/infrastructure/src/guards/` | 骨架 + chaos 测试 | **冻结**：未接 RunEngine |
| ACL / v4-adapter | `packages/infrastructure/src/acl/` | v4 兼容实验 | **冻结** |
| shadow-mode | `packages/infrastructure/src/shadow/` | 引用 application | **测试专用** |
| v4-to-v5 migration | `packages/infrastructure/src/migration/` | 一次性迁移脚本 | **保留**至 D1 后评估 |

---

## `@butler/ports` — Port 契约

保留；新外部边界（MCP Host、第二 Channel）应先在 Port 定义，再在 `adapters` 实现，最后 **opt-in** 注册到 `CapabilityRegistry`。

---

## 条件准入能力（P3 前置，当前 scaffold）

| 能力 | Env | 生产入口 | 备注 |
|------|-----|----------|------|
| MCP 工具 | `BUTLER_V5_MCP_ENABLED=1` + `BUTLER_V5_MCP_URL` 或 stub 名 | `apps/api/src/mcp-bootstrap.ts` | HTTP `tools/list` + `tools/call`；启动时注入 `wiring.mcp` |
| 通用 Channel intake | `BUTLER_V5_CHANNEL_API_ENABLED=1` | `POST /v1/channel/inbound` | 复用 `runButlerLoop`；非 Slack/Telegram 专用适配 |
| 原生 iLink | `BUTLER_V5_ILINK_ENABLED=1` | `apps/api/src/ilink-poller.ts` | 已交付，仍 opt-in |
| bubblewrap | `BUTLER_V5_SANDBOX=bubblewrap` | `workspace-tools.ts` | P2 已交付 |

第二消息 Channel（Slack/Telegram 等）**未立项**；不得创建第二套 Run 状态机。

---

## 删除/归档前检查

1. 架构测试与层依赖仍通过  
2. `v5-production-architecture` 未声称该包在生产链上  
3. 无 `apps/api` 或 `packages/runtime` 的 import 残留  
4. Owner 确认（application/infrastructure 删除需单独决策）

---

## 相关

- [`v5-post-boundary-roadmap-2026-08.md`](v5-post-boundary-roadmap-2026-08.md) P0 交付项「未接线包清单」  
- [`v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md) MCP / 多 Channel 条件准入
