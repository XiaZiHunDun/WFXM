// domain/event-sourcing.ts
// 事件溯源 + CQRS 纯函数 §10

import type { ConversationEvent, ConversationState } from "./conversation/types.js"
import { transition } from "./conversation/transitions.js"

// ─── 事件 → 状态投影（纯函数）§10.1 ────────────────────
export function projectConversation(events: readonly ConversationEvent[]): ConversationState {
  return events.reduce(transition, { _tag: "Idle" } as ConversationState)
}

// ─── CQRS 读模型（从事件流投影）§10.2 ──────────────────
export function loadConversation(events: readonly ConversationEvent[]): ConversationState {
  return projectConversation(events)
}

// ─── DeltaChannel 增量检查点 [OPT-12] §10.4 ────────────
export type DeltaChannel = {
  readonly streamId: string
  readonly lastVersion: number
}

export function delta(
  channel: DeltaChannel,
  events: readonly ConversationEvent[],
): readonly ConversationEvent[] {
  return events.slice(channel.lastVersion)
}

// ─── R2.3 通用领域事件 + Event Envelope [spec §7.1, §7.2] ──────
// 通用领域事件：所有事件载体（conversation / project / workflow / approval / memory）的最小可识别契约
export type DomainEvent = { readonly _tag: string } & Record<string, unknown>

// 流类型 — Event Envelope 上游分类
export type StreamType = "conversation" | "project" | "workflow" | "approval" | "memory"

// 触发者 / 上游系统引用
export type ActorRef = {
  readonly kind: "owner" | "agent" | "system"
  readonly id: string
}

// Event Envelope — 事件溯源统一信封（spec §7.2）
export interface EventEnvelope {
  readonly eventId: string
  readonly eventType: string
  readonly eventVersion: number
  readonly streamId: string
  readonly streamType: StreamType
  readonly streamVersion: number
  readonly occurredAt: string
  readonly causationId: string | null
  readonly correlationId: string
  readonly actor: ActorRef
  readonly payload: unknown
}

// 进程内单调递增序号（用于 eventId 防重复）；MVP 用 module-level 计数器
let envelopeSeq = 0

export function buildEnvelope(input: {
  streamId: string
  streamType: StreamType
  event: DomainEvent
}): EventEnvelope {
  envelopeSeq += 1
  const now = new Date().toISOString()
  const eventTag = (input.event as { _tag: string })._tag
  return {
    eventId: `evt-${Date.now()}-${envelopeSeq}`,
    eventType: eventTag,
    eventVersion: 1,
    streamId: input.streamId,
    streamType: input.streamType,
    streamVersion: 1,
    occurredAt: now,
    causationId: null,
    correlationId: `corr-${Date.now()}-${envelopeSeq}`,
    actor: { kind: "system", id: "domain" },
    payload: input.event,
  }
}

// 验证结果 — 不抛异常（tests/guard/no-layer-violation 禁止 throw）
export type EnvelopeValidation =
  { readonly ok: true } | { readonly ok: false; readonly reason: string }

export function validateEnvelope(env: EventEnvelope): EnvelopeValidation {
  if (env.eventVersion !== 1) {
    return { ok: false, reason: `unsupported eventVersion ${env.eventVersion}` }
  }
  if (env.streamVersion < 1) {
    return { ok: false, reason: "streamVersion must be >= 1" }
  }
  if (!env.correlationId) {
    return { ok: false, reason: "correlationId required" }
  }
  return { ok: true }
}
