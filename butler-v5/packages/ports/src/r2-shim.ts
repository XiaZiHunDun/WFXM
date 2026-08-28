/**
 * v5 R2 Effect Tag fixture shim (since R12 commit 33af1722, 2026-08-28).
 *
 * R12 cleanup removed these 14 Tag class definitions from
 * `packages/ports/src/index.ts` (production v5 does not consume them; the
 * runtime flow is async/await + `/core/*` ports per DESIGN §7).
 *
 * Archived scaffolding (`_archive/packages/**`) still has mock/fixture code
 * importing these Tags (e.g. `Layer.succeed(LLMService, LLMService.of(...))`).
 * To keep `pnpm test:archived` green without rewriting archived test
 * fixtures, this shim restores all 14 R2 Tag class definitions verbatim from
 * pre-R12 commit `278a0cc7`.
 *
 * ⚠️ Production v5 code must NOT import this file. Verify via:
 *   grep -RIn "@butler/ports" butler-v5/packages butler-v5/apps butler-v5/cli
 * Hits under `_archive/` are expected; hits elsewhere are policy violations.
 *
 * 设计说明：14 个 R2 Tag 中含 DESIGN §12 明文不建设的 `MemoryService.dream`、
 * §2 明文不预建的 `WorkflowService.start/send/merge`、AGENTS §0 划分属
 * 开发仓库非 runtime 的 `GuardService` 10 项（含 `[G-9]/[G-10]`）。这些 Tag
 * 类保留仅作 fixture 兼容性，不进入 production runtime path。
 */

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
