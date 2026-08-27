import type { RunTrigger, TrustLevel, TriggerSource } from "./types.js"

export interface BuildRunTriggerInput {
  readonly subject: string
  readonly source: TriggerSource
  readonly conversationRef?: string | null
  readonly payload?: Readonly<Record<string, unknown>>
  readonly trustLevel?: TrustLevel
  readonly idempotencyKey: string
}

export function buildRunTrigger(input: BuildRunTriggerInput): RunTrigger {
  return {
    subject: input.subject.trim(),
    source: input.source,
    conversationRef: input.conversationRef ?? null,
    payload: input.payload ?? {},
    trustLevel: input.trustLevel ?? "untrusted",
    idempotencyKey: input.idempotencyKey.trim(),
  }
}

export function buildWechatRunTrigger(input: {
  readonly userId: string
  readonly conversationId: string
  readonly content: string
  readonly messageId?: string
  readonly trustLevel?: TrustLevel
  readonly extraPayload?: Readonly<Record<string, unknown>>
}): RunTrigger {
  return buildRunTrigger({
    subject: input.userId,
    source: "channel",
    conversationRef: input.conversationId,
    payload: {
      channelId: "wechat",
      content: input.content,
      ...(input.extraPayload ?? {}),
    },
    trustLevel: input.trustLevel ?? "trusted",
    idempotencyKey: input.messageId ?? `wechat-${input.conversationId}-${Date.now()}`,
  })
}

export function buildChannelRunTrigger(input: {
  readonly channelId: string
  readonly fromSubject: string
  readonly conversationId: string
  readonly content: string
  readonly messageId?: string
}): RunTrigger {
  return buildRunTrigger({
    subject: input.fromSubject,
    source: "webhook",
    conversationRef: input.conversationId,
    payload: {
      channelId: input.channelId,
      content: input.content,
    },
    trustLevel: "untrusted",
    idempotencyKey: input.messageId ?? `channel-${input.channelId}-${input.conversationId}`,
  })
}

export function buildApiRunTrigger(input: {
  readonly subject: string
  readonly conversationId?: string
  readonly payload?: Readonly<Record<string, unknown>>
  readonly idempotencyKey: string
}): RunTrigger {
  return buildRunTrigger({
    subject: input.subject,
    source: "api",
    conversationRef: input.conversationId ?? null,
    payload: input.payload ?? {},
    trustLevel: "owner",
    idempotencyKey: input.idempotencyKey,
  })
}

export function buildCliRunTrigger(input: {
  readonly subject: string
  readonly goal: string
  readonly idempotencyKey: string
}): RunTrigger {
  return buildRunTrigger({
    subject: input.subject,
    source: "cli",
    conversationRef: null,
    payload: { goal: input.goal },
    trustLevel: "owner",
    idempotencyKey: input.idempotencyKey,
  })
}

export function buildTaskRunTrigger(input: {
  readonly subject: string
  readonly taskId: string
  readonly goal: string
  readonly conversationId: string
  readonly idempotencyKey: string
  readonly procedureId?: string | null
  readonly stepKey?: string | null
}): RunTrigger {
  return buildRunTrigger({
    subject: input.subject,
    source: "task",
    conversationRef: input.conversationId,
    payload: {
      taskId: input.taskId,
      goal: input.goal,
      ...(input.procedureId ? { procedureId: input.procedureId } : {}),
      ...(input.stepKey ? { stepKey: input.stepKey } : {}),
    },
    trustLevel: "owner",
    idempotencyKey: input.idempotencyKey,
  })
}

export function validateRunTrigger(
  trigger: RunTrigger,
): { readonly ok: true } | { readonly ok: false; readonly reason: string } {
  if (!trigger.subject.trim()) return { ok: false, reason: "subject is required" }
  if (!trigger.idempotencyKey.trim()) return { ok: false, reason: "idempotencyKey is required" }
  if (trigger.source === "channel" || trigger.source === "webhook") {
    if (!trigger.conversationRef?.trim()) {
      return { ok: false, reason: "conversationRef is required for channel/webhook triggers" }
    }
  }
  return { ok: true }
}

/** Persist RunTrigger metadata alongside the bounded run budget. */
export function runBudgetWithTrigger(
  trigger: RunTrigger,
  base: Readonly<Record<string, unknown>> = {},
): Readonly<Record<string, unknown>> {
  return {
    maxSteps: 5,
    ...base,
    trustLevel: trigger.trustLevel,
    triggerPayload: trigger.payload,
    ...(trigger.conversationRef ? { conversationRef: trigger.conversationRef } : {}),
  }
}
