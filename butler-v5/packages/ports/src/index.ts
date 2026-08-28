// packages/ports/src/index.ts
//
// v5 Core Ports barrel — DESIGN §7 物化的 Port 接口。
//
// 历史：本文件 2026-08-28 之前承载 R2 时代的 14 个 Effect Tag 接口
// （LLMService / ToolExecutor / EventStoreService / OutboxService /
//  SnapshotService / ProjectionService / LoopInterrupt / GuardService /
//  WeChatGateway / MCPDiscovery / ProjectService / MemoryService /
//  WorkflowService / Config）。生产 delivery shell 走 async/await + 直调
// `@butler/persistence`，并不经过 Context.Tag 注入面。
//
// R12 simplification（v5-postgres-adapter-port-migration-2026-08 PRD §3 +
// 见本批次 commit `278a0cc7` Phase 2 与紧接此 commit）实证：
//  - 全部 14 Tag 类在 production 代码中零 caller（postgres 适配器与
//    Config Tag 唯一消费面已 `git rm`，见 `tests/contracts/test_port_stability.test.ts`）；
//  - 全部 R2 Tag 类从本文件移除，R2 Tag 总线归档历史。
//  - `port-catalog.md` §2 R2 迁移看板当前为空（无待迁条目）。
//
// 新代码请直接 import 物化的 Core 端口：
//
//   import { ClockPort, systemClock, fixedClock }
//     from "@butler/ports/core/clock.js"
//   import type { CredentialProvider, isValidCredentialName }
//     from "@butler/ports/core/credential-provider.js"
//   import type { EventStorePort }
//     from "@butler/ports/core/event-store.js"
//   import type { OutboxPort }
//     from "@butler/ports/core/outbox.js"
//   import type { SnapshotPort }
//     from "@butler/ports/core/snapshot.js"
//   import type { ProjectionPort }
//     from "@butler/ports/core/projection.js"
//
// 完整 port → consumer → producer 映射与维护规则见
// `packages/ports/port-catalog.md`；顶层决策、不变量、"ports-stable ×
// real-need driven"准则见 `DESIGN.md §7`。

export * from "./core/clock.js"
export * from "./core/credential-provider.js"
export * from "./core/event-store.js"
export * from "./core/outbox.js"
export * from "./core/snapshot.js"
export * from "./core/projection.js"
