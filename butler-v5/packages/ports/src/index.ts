// packages/ports/src/index.ts
//
// v5 Ports barrel — DESIGN §7 物化的 Core 端口（thin barrel）。
//
// 历史：本文件 2026-08-28 R12 之前承载 R2 时代的 14 个 Effect Tag 接口
// （LLMService / ToolExecutor / EventStoreService / OutboxService /
//  SnapshotService / ProjectionService / LoopInterrupt / GuardService /
//  WeChatGateway / MCPDiscovery / ProjectService / MemoryService /
//  WorkflowService / Config）。生产 delivery shell 走 async/await + 直调
// `@butler/persistence`，并不经过 Context.Tag 注入面。
//
// D61 T5（audit #2 F-07）：删除 r2-shim.ts（280 行 + 14 个 R2 Tag 类） +
// 该 barrel re-export。零 production caller，archive scaffolding 已不再
// 引用（archived fixtures 不在本仓库 active tsconfig 中）。
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
export * from "./core/model-port.js"
export * from "./core/repository.js"
export * from "./core/channel.js"
export * from "./core/event-store.js"
export * from "./core/outbox.js"
export * from "./core/snapshot.js"
export * from "./core/projection.js"
