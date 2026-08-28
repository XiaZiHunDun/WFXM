// packages/ports/src/index.ts
//
// v5 Ports barrel — DESIGN §7 物化的 Core 端口（thin barrel）
//   + R2 Effect Tag fixture shim（仅 archived `pnpm test:archived` 使用）。
//
// 历史：本文件 2026-08-28 R12 之前承载 R2 时代的 14 个 Effect Tag 接口
// （LLMService / ToolExecutor / EventStoreService / OutboxService /
//  SnapshotService / ProjectionService / LoopInterrupt / GuardService /
//  WeChatGateway / MCPDiscovery / ProjectService / MemoryService /
//  WorkflowService / Config）。生产 delivery shell 走 async/await + 直调
// `@butler/persistence`，并不经过 Context.Tag 注入面。
//
// R12 实证（commit `33af1722`）：
//   - 全部 14 Tag 类在 production 代码中零 caller（postgres 适配器与
//     Config Tag 唯一消费面已 `git rm`）；
//   - 生产 v5 不再需要这些 Tag 类，但 archived scaffolding 下
//     `_archive/packages/**` 的 mock/fixture 代码仍在
//     `import { LLMService } from "@butler/ports"` 形式（用于
//     `Layer.succeed(Tag, Tag.of(...))` 模式）。
//
// 当前 barrel 由两层组成（顺序重要——R2 shim 排在末尾，扩展同名符号
// 会被后续覆盖）：
//
//   1. /core/* — v5 物化的 6 个 Core Port（DESIGN §7：Clock / Credential
//      Provider / Event Store / Outbox / Snapshot / Projection）
//   2. /r2-shim — 14 个 R2 Effect Tag 类 fixture shim（见 `r2-shim.ts`
//      注释为何保留、为何不算违反 invariant 16）
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
export * from "./core/channel.js"
export * from "./core/event-store.js"
export * from "./core/outbox.js"
export * from "./core/snapshot.js"
export * from "./core/projection.js"
export * from "./r2-shim.js"
