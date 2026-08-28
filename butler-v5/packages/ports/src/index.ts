// ──────────────────────────────────────────────────────────────────────
//  ⚠️ @deprecated since 2026-08-28 — Effect Tag 端口正逐步迁移至 /core/*
// ──────────────────────────────────────────────────────────────────────
//
// 本文件（packages/ports/src/index.ts）仍提供 R2 时代的 Effect Tag 接口
// (LLMService / ToolExecutor / EventStoreService / OutboxService /
//  SnapshotService / ProjectionService / LoopInterrupt / GuardService /
//  WeChatGateway / MCPDiscovery / ProjectService / MemoryService /
//  WorkflowService / Config)，因为 `packages/adapters/src/postgres/*`
// 的 R2 适配器仍在引用（OutboxService / EventStoreService /
// SnapshotService / ProjectionService / Config）。
//
// 新代码请直接 import 下方的物化 Core 端口：
//
//   import { ClockPort, systemClock, fixedClock }
//     from "@butler/ports/core/clock.js"
//   import type { CredentialProvider, isValidCredentialName }
//     from "@butler/ports/core/credential-provider.js"
//   import type { EventStorePort }
//     from "@butler/ports/core/event-store.js"
//
// 等 postgres 适配器迁移到 /core/* 后，本文件 Effect Tag 类可删除并归档
// 到 _archive/packages/ports-effect-tag-scaffold/。详见
// packages/ports/port-catalog.md 与 DESIGN §7.1。
//
// 旧 header（保留以便历史追溯）：
// ports/index.ts
// Effect Tag 接口定义 — 所有副作用通过 Tag 注入，实现见 infrastructure/

import { Context, type Effect, type Stream } from "effect"
import type {
  ConversationEvent,
  ContractSnapshot,
  DiscoveredTool,
  IntentReceipt,
  LinkedFilesSpec,
  LoopError,
  MemoryRecord,
  Message,
  ToolCall,
  ToolResult,
  DreamPhase,
  DreamResult,
  DelegateTaskInput,
} from "@butler/domain"

// ─── LLM 服务 ───────────────────────────────────────────
export class LLMService extends Context.Tag("LLMService")<
  LLMService,
  {
    readonly complete: (messages: readonly Message[]) => Effect.Effect<Message, LoopError>
    readonly stream: (messages: readonly Message[]) => Stream.Stream<Message, LoopError>
  }
>() {}

// ─── 工具执行器 ─────────────────────────────────────────
export class ToolExecutor extends Context.Tag("ToolExecutor")<
  ToolExecutor,
  {
    readonly execute: (call: ToolCall) => Effect.Effect<ToolResult, LoopError>
  }
>() {}

// ─── 事件存储 ───────────────────────────────────────────
export class EventStoreService extends Context.Tag("EventStoreService")<
  EventStoreService,
  {
    readonly append: (
      streamId: string,
      events: readonly ConversationEvent[],
    ) => Effect.Effect<void, LoopError>
    readonly load: (streamId: string) => Effect.Effect<readonly ConversationEvent[], LoopError>
    readonly subscribe: () => Stream.Stream<ConversationEvent, never>
  }
>() {}

// ─── Outbox（持久化 outbox 消息队列端口） ────────────────
// Adapter 层（R5.1 postgres adapter）通过该端口消费 R3 persistence 的
// `enqueueOutbox` / `claimOutbox` / `completeOutbox` / `failOutbox` /
// `runWorkerOnce` 公共 API。规格 §7.3 outbox 协议入口。
export class OutboxService extends Context.Tag("OutboxService")<
  OutboxService,
  {
    readonly enqueue: (input: {
      readonly streamId: string
      readonly aggregateType: string
      readonly payload: Record<string, unknown>
    }) => Effect.Effect<{ readonly messageId: string }, LoopError>
    readonly claim: () => Effect.Effect<
      readonly { readonly messageId: string; readonly streamId: string }[],
      LoopError
    >
    readonly complete: (messageId: string) => Effect.Effect<void, LoopError>
    readonly fail: (messageId: string, error: string) => Effect.Effect<void, LoopError>
    readonly runWorker: (
      handler: (msg: { readonly messageId: string; readonly payload: unknown }) => Promise<void>,
    ) => Effect.Effect<number, LoopError>
  }
>() {}

// ─── Snapshot（per-stream 状态快照端口） ──────────────────
// Adapter 层通过该端口消费 R3 persistence 的 `loadSnapshot` / `saveSnapshot`。
export class SnapshotService extends Context.Tag("SnapshotService")<
  SnapshotService,
  {
    readonly load: (
      streamId: string,
    ) => Effect.Effect<
      { readonly streamVersion: number; readonly payload: unknown } | null,
      LoopError
    >
    readonly save: (
      streamId: string,
      streamVersion: number,
      payload: Record<string, unknown>,
    ) => Effect.Effect<void, LoopError>
  }
>() {}

// ─── Projection（读模型端口） ─────────────────────────────
// Adapter 层通过该端口消费 R3 persistence 的 `applyProjection` /
// `rebuildProjection` / `registerProjection`。
export class ProjectionService extends Context.Tag("ProjectionService")<
  ProjectionService,
  {
    readonly apply: (streamId: string, name: string) => Effect.Effect<void, LoopError>
    readonly rebuild: (streamId: string, name: string) => Effect.Effect<void, LoopError>
    readonly register: (name: string, handler: unknown) => Effect.Effect<void, never>
  }
>() {}

// ─── Loop 中断/恢复 ─────────────────────────────────────
export class LoopInterrupt extends Context.Tag("LoopInterrupt")<
  LoopInterrupt,
  {
    readonly interrupt: (loopId: string, reason: string) => Effect.Effect<void, never>
    readonly resume: (loopId: string, input: unknown) => Effect.Effect<void, never>
    readonly awaitExternal: <A>(prompt: string, timeoutMs: number) => Effect.Effect<A, LoopError>
  }
>() {}

// ─── 防错守卫（单 Tag 合并 10 条 GUARD） ────────────────
export class GuardService extends Context.Tag("GuardService")<
  GuardService,
  {
    readonly issueReceipt: (input: {
      readonly intent: string
      readonly evidenceFiles: readonly string[]
      readonly locDelta: { readonly added: number; readonly removed: number }
      readonly authorAgent: string
    }) => Effect.Effect<IntentReceipt, LoopError>

    readonly checkLoadBearing: (
      path: string,
      op: "write" | "delete",
    ) => Effect.Effect<{ readonly allowed: boolean; readonly reason?: string }, LoopError>

    readonly checkOwnerOnline: (action: {
      readonly toolId: string
      readonly category: "read" | "write" | "execute" | "delegate"
    }) => Effect.Effect<
      { readonly decision: "allow" | "queue" | "deny"; readonly reason: string },
      never
    >

    readonly verifyHumanSig: (sig: string, payload: unknown) => Effect.Effect<boolean, never>

    readonly verifyChain: (
      spec: LinkedFilesSpec,
      files: readonly string[],
    ) => Effect.Effect<
      { readonly completeness: number; readonly missing: readonly string[] },
      never
    >

    readonly pickVerification: (
      delta: { readonly added: number; readonly removed: number },
      isGen: boolean,
    ) => Effect.Effect<"Fast" | "Standard", never>

    readonly checkRoleSeparation: (
      author: string,
      reviewer: string,
    ) => Effect.Effect<{ readonly ok: boolean; readonly reason?: string }, never>

    readonly heal: <A, E>(
      effect: Effect.Effect<A, E>,
      options: { readonly maxRetry: number; readonly fallback?: () => Effect.Effect<A, E> },
    ) => Effect.Effect<A, E | LoopError>

    readonly archiveAntiPattern: (pattern: string, evidence: unknown) => Effect.Effect<void, never> // [G-9]
    readonly scheduleChaos: (scenario: string, cron: string) => Effect.Effect<void, never> // [G-10]
    readonly loadContract: () => Effect.Effect<ContractSnapshot, never> // 契约加载
  }
>() {}

// ─── 微信网关 ───────────────────────────────────────────
export class WeChatGateway extends Context.Tag("WeChatGateway")<
  WeChatGateway,
  {
    readonly send: (to: string, content: string) => Effect.Effect<void, never>
    readonly receive: () => Stream.Stream<WeChatMessage, never>
    readonly verifySignature: (
      signature: string,
      timestamp: string,
      nonce: string,
    ) => Effect.Effect<boolean, never>
  }
>() {}

export type WeChatMessage = {
  readonly from: string
  readonly to: string
  readonly content: string
  readonly msgType: "text" | "image" | "voice"
  readonly createTime: number
}

// ─── MCP 动态发现 [OPT-6] ───────────────────────────────
export class MCPDiscovery extends Context.Tag("MCPDiscovery")<
  MCPDiscovery,
  {
    readonly discover: () => Effect.Effect<readonly DiscoveredTool[], never>
    readonly invalidate: (server: string) => Effect.Effect<void, never>
  }
>() {}

// ─── 项目服务 ───────────────────────────────────────────
export class ProjectService extends Context.Tag("ProjectService")<
  ProjectService,
  {
    readonly loadSpec: (specRef: string) => Effect.Effect<unknown, LoopError>
    readonly delegateTask: (input: DelegateTaskInput) => Effect.Effect<IntentReceipt, LoopError>
  }
>() {}

// ─── 记忆服务 ───────────────────────────────────────────
export class MemoryService extends Context.Tag("MemoryService")<
  MemoryService,
  {
    readonly search: (q: string, k: number) => Effect.Effect<readonly MemoryRecord[], never>
    readonly dream: (phase: DreamPhase) => Effect.Effect<DreamResult, never>
  }
>() {}

// ─── 工作流服务 ─────────────────────────────────────────
export class WorkflowService extends Context.Tag("WorkflowService")<
  WorkflowService,
  {
    readonly start: (spec: LinkedFilesSpec) => Effect.Effect<string, LoopError>
    readonly send: (cmd: {
      readonly toAgent: string
      readonly message: string
      readonly contextRef?: string
    }) => Effect.Effect<void, LoopError>
    readonly merge: (id: string) => Effect.Effect<void, LoopError>
  }
>() {}

// ─── 配置 ───────────────────────────────────────────────
export class Config extends Context.Tag("Config")<Config, AppConfig>() {}

// ─── 配置 Shape ─────────────────────────────────────────
export type AppConfig = {
  readonly loop: {
    readonly maxIterations: number
    readonly timeoutMs: number
  }
  readonly guards: {
    readonly ownerOfflineThresholdMs: number
    readonly chaosEnabled: boolean
  }
  readonly llm: {
    readonly primary: string
    readonly fallback: string
  }
  readonly db: {
    readonly url: string
    readonly maxConnections: number
  }
  readonly wechat: {
    readonly token: string
    readonly appId: string
    readonly appSecret: string
  }
}

// ─── /core/* 物化端口（DESIGN §7 P5 实施，2026-08-28）────────────
// 新代码请优先使用这些纯 TS 接口（无 Effect 依赖、可独立单测）。
// 与上文 R2 Effect Tag 类并存；B-soft 路径详见文件顶 deprecation 注释
// 与 packages/ports/port-catalog.md。
export * from "./core/clock.js"
export * from "./core/credential-provider.js"
export * from "./core/event-store.js"
