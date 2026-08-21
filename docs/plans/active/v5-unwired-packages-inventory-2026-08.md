# Butler v5 未接线包清单（2026-08）

> **状态**：Active（归档执行中）  
> **用途**：记录不在生产调用链上的 v5 包与模块  
> **架构事实**：[`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)

---

## 生产路径（已接线）

```text
butler-v5/cli + apps/api
  → packages/runtime（RunEngine / PolicyGate / approval-runtime）
  → packages/adapters（LLM / WeChat / sandbox / MCP client 适配器）
  → packages/persistence（唯一 schema + RuntimeStore）
  → packages/domain（类型 / 策略 / RunTrigger / MCP manifest）
```

---

## `@butler/application` — **已全部归档**

| 模块 | 路径 | 状态 |
|------|------|------|
| `run-loop` | `_archive/run-loop/` | 已归档 |
| `delegate-task` | `_archive/delegate-task/` | 已归档 |
| `run-workflow` | `_archive/run-workflow/` | 已归档 |
| `dream` | `_archive/dream/` | 已归档 |

`packages/application/src/index.ts` 仅保留空导出；生产 Loop 在 `runtime` + `wechat-inbound-butler`。

---

## `@butler/infrastructure` — 归档 + 保留

| 模块 | 路径 | 状态 |
|------|------|------|
| guards / acl / shadow / patch | `_archive/*` | 已归档 |
| persistence (Drizzle 并行 schema) | `_archive/persistence/` | 已归档 |
| mcp / llm / wechat stub | `_archive/*` | 已归档 |
| `migration/v4-to-v5` | `src/migration/` | **保留**至 D1 |
| `layers.ts` | `src/layers.ts` | Effect 示例；无生产消费者 |

---

## P3 接缝（草案已落地，未改生产行为）

| 接缝 | 位置 | 状态 |
|------|------|------|
| `RunTrigger` 构建器 | `packages/domain/src/runtime/run-trigger.ts` | 草案 + 测试 |
| MCP manifest 解析 | `packages/domain/src/mcp/manifest.ts` | 草案 + 测试 |
| MCP server consent | `packages/runtime/src/mcp-consent.ts` + `mcp-bootstrap` | opt-in `BUTLER_V5_MCP_REQUIRE_CONSENT` |

---

## 条件准入能力（生产 opt-in）

MCP、Slack/Telegram、iLink、bubblewrap、Channel API — 见 [`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md) §6。

---

## 删除/归档前检查

1. 架构测试与层依赖仍通过  
2. 无 `apps/api` 或 `packages/runtime` 对归档模块的 import  
3. Owner 确认彻底删除（当前策略：**归档保留**，不删 git 历史）
