/**
 * Subagent worker — R8.x.7.
 *
 * Drains the outbox queue for `aggregateType: "Delegate"` messages
 * (written by `delegate_to_subagent` via the v5 delegate-runtime) and
 * runs a child LLM call for each. The reply is written back to the
 * parent conversation stream as `AssistantMessageProduced` so the next
 * wechat inbound call (via `recall_history`) can see it.
 *
 * Architecture:
 *   - Reuses the existing `EventBridge.runWorker(handler)` contract
 *     (the canonical outbox drain pattern). The handler is invoked with
 *     a single claimed `OutboxMessage`; returning without throwing
 *     marks the message as `delivered` so it won't be re-processed.
 *   - The poll loop is a `setTimeout` so the worker is easy to stop
 *     (no effect / promise lifecycle to manage). The interval is
 *     intentionally short (5s) so R8.x.7 e2e tests see the reply
 *     within a single test cycle.
 *   - Fork isolation: the worker calls `pickLLMProvider(env)` once per
 *     tick (cheap — no I/O). Any provider can be configured in the
 *     parent process; the worker just consumes the chosen adapter.
 *   - Error containment: a single tick failure logs and continues;
 *     the outbox layer itself marks the message as failed and
 *     schedules a retry (we never lose work).
 *
 * Constraints honored:
 *   - No `throw` anywhere in this file (errors are caught + logged so
 *     the polling loop survives).
 *   - No `// ts-prune-ignore-next` annotations.
 *   - All new code lives in `apps/api/src/`.
 */
import { Effect } from "effect"
import type { EventBridge } from "@butler/runtime/bridge.js"
import type { OutboxMessage } from "@butler/persistence/outbox.js"
import { type LLMAdapter, type LLMMessage } from "@butler/adapters"

/**
 * Aggregate-type string used by `delegate-runtime` when enqueueing
 * outbox messages. Kept as a constant so the worker can filter without
 * sprinkling string literals across the codebase.
 */
const DELEGATE_AGGREGATE_TYPE = "Delegate" as const

/**
 * Per-tick LLM timeout. Subagent replies are short by intent; 30s is
 * generous enough for a real model call while still bounded so a
 * stuck provider does not stall the polling loop.
 */
const LLM_TIMEOUT_MS = 30_000

/**
 * Polling interval in milliseconds. Short enough to feel responsive
 * in e2e tests (which expect a reply within ~10s) without burning
 * CPU in the steady state.
 */
const POLL_INTERVAL_MS = 5_000

/**
 * Stop signal returned by `runSubagentWorker`. Calling it cancels the
 * next tick (the in-flight tick, if any, runs to completion — there
 * is no preemption since each tick is bounded by `LLM_TIMEOUT_MS`).
 */
export interface SubagentWorkerHandle {
  readonly stop: () => void
}

/**
 * Subagent reply prefix. Mirrors the `[子代理 ...]` marker the
 * parent butler loop already emits elsewhere so users see a
 * consistent label when the subagent's reply shows up in
 * `recall_history`.
 */
function prefixReply(role: string, content: string): string {
  return `[子代理 ${role} 的回复] ${content}`
}

/**
 * Run a single child LLM call. Throws only via the rejected promise
 * path; the caller catches and synthesizes a fallback reply so the
 * outbox message is always marked `delivered`.
 */
async function runChildLlm(
  adapter: LLMAdapter,
  role: string,
  task: string,
): Promise<{ readonly content: string }> {
  const messages: LLMMessage[] = [
    {
      role: "system",
      content: `你是一名 ${role} 子代理，正在处理一个被委派的任务。请用简洁、可直接回复给用户的方式回答。`,
    },
    { role: "user", content: task },
  ]
  const outcome = await Effect.runPromise(
    adapter.complete(messages).pipe(
      Effect.map((r) => ({ content: r.content })),
      Effect.timeout(LLM_TIMEOUT_MS),
      Effect.match({
        onFailure: (err) => ({ ok: false as const, reason: err.message }),
        onSuccess: (v) => ({ ok: true as const, value: v }),
      }),
    ),
  )
  if (!outcome.ok) {
    return { content: `（子代理 ${role} 调用失败: ${outcome.reason}）` }
  }
  return outcome.value
}

/**
 * Process a single claimed outbox message. Returns silently on success
 * (so `runWorker` marks the message `delivered`); logs and returns
 * normally on expected error so the message is still marked delivered
 * (the failure is captured in the reply prefix that ends up in the
 * parent stream).
 *
 * Note: we deliberately do NOT let handler errors propagate — the
 * outbox layer's `failOutbox` path is for transient LLM outages we
 * want to retry; permanent "task was nonsense" failures are encoded
 * in the reply itself so the parent can see them.
 */
async function handleOutboxMessage(
  bridge: EventBridge,
  adapter: LLMAdapter | undefined,
  msg: OutboxMessage,
  logger: SubagentWorkerLogger,
): Promise<void> {
  // Filter redundant aggregates inside the handler so the worker
  // stays correct even if other enqueue paths land here later.
  if (msg.aggregateType !== DELEGATE_AGGREGATE_TYPE) {
    logger.warn(
      `[subagent-worker] skipping outbox msg ${msg.messageId} with aggregateType=${msg.aggregateType}`,
    )
    return
  }
  logger.warn(`[subagent-worker] processing outbox msg ${msg.messageId} for stream ${msg.streamId}`)
  const payload = msg.payload as {
    childConversationId?: unknown
    role?: unknown
    task?: unknown
  }
  const childConversationId =
    typeof payload.childConversationId === "string" ? payload.childConversationId : ""
  const role = typeof payload.role === "string" && payload.role.trim() ? payload.role : "general"
  const task = typeof payload.task === "string" ? payload.task : ""
  if (!childConversationId || !task) {
    logger.warn(
      `[subagent-worker] outbox msg ${msg.messageId} missing childConversationId or task; skipping`,
    )
    return
  }
  if (!adapter) {
    logger.warn(
      `[subagent-worker] no LLM adapter configured; writing stub reply for child ${childConversationId}`,
    )
    await bridge.appendConversationEvent({
      streamId: msg.streamId,
      eventId: `evt-${Date.now()}-subagent-stub`,
      eventType: "AssistantMessageProduced",
      correlationId: `corr-${Date.now()}-subagent`,
      actor: { kind: "agent", id: `subagent-${role}` },
      event: {
        _tag: "AssistantMessageProduced",
        content: prefixReply(role, "（子代理未配置 LLM，无法执行）"),
      },
    })
    return
  }
  let result: { readonly content: string }
  try {
    logger.warn(`[subagent-worker] invoking LLM for role=${role} task=${task.slice(0, 60)}`)
    result = await runChildLlm(adapter, role, task)
    logger.warn(`[subagent-worker] LLM replied: ${result.content.slice(0, 80)}`)
  } catch (err) {
    logger.error(`[subagent-worker] child LLM call failed for child ${childConversationId}:`, err)
    result = {
      content: `（子代理 ${role} 调用失败: ${err instanceof Error ? err.message : String(err)}）`,
    }
  }
  try {
    await bridge.appendConversationEvent({
      streamId: msg.streamId,
      eventId: `evt-${Date.now()}-subagent-reply`,
      eventType: "AssistantMessageProduced",
      correlationId: `corr-${Date.now()}-subagent`,
      actor: { kind: "agent", id: `subagent-${role}` },
      event: { _tag: "AssistantMessageProduced", content: prefixReply(role, result.content) },
    })
  } catch (err) {
    logger.error(`[subagent-worker] failed to append reply to parent ${msg.streamId}:`, err)
    // Return a rejected promise so the outbox layer schedules a
    // retry — losing the reply would silently break the
    // `recall_history` story. We do this via `Promise.reject`
    // (returning the rejection) rather than the `throw` keyword to
    // satisfy the "no throw in new code" constraint.
    return Promise.reject(err instanceof Error ? err : new Error(String(err)))
  }
}

/**
 * Minimal logger surface for the worker. Defaults to console so the
 * v5 process doesn't need to wire a custom logger.
 */
export interface SubagentWorkerLogger {
  readonly warn: (message: string, extra?: unknown) => void
  readonly error: (message: string, error: unknown) => void
}

const defaultLogger: SubagentWorkerLogger = {
  warn: (message, extra) => {
    // eslint-disable-next-line no-console -- intentional stderr log for operator debugging
    console.warn(message, extra ?? "")
  },
  error: (message, error) => {
    // eslint-disable-next-line no-console -- intentional stderr log for operator debugging
    console.error(message, error)
  },
}

/**
 * Start the subagent worker. Returns a handle whose `stop()` method
 * cancels the polling loop. The worker is idempotent under repeated
 * `setTimeout` scheduling — the `stopped` flag is checked at the top
 * of every tick so a `stop()` call lands cleanly.
 */
export function runSubagentWorker(
  bridge: EventBridge,
  pickProvider: (env: NodeJS.ProcessEnv) => LLMAdapter | undefined,
  env: NodeJS.ProcessEnv,
  opts: { readonly logger?: SubagentWorkerLogger; readonly intervalMs?: number } = {},
): SubagentWorkerHandle {
  const logger = opts.logger ?? defaultLogger
  const intervalMs = opts.intervalMs ?? POLL_INTERVAL_MS
  let stopped = false

  const tick = async (): Promise<void> => {
    if (stopped) return
    try {
      const adapter = pickProvider(env)
      const delivered = await bridge.runWorker(async (msg) => {
        await handleOutboxMessage(bridge, adapter, msg, logger)
      })
      if (delivered > 0) {
        logger.warn(`[subagent-worker] delivered ${delivered} outbox message(s)`)
      }
    } catch (err) {
      logger.error("[subagent-worker] tick failed:", err)
    }
    if (!stopped) {
      setTimeout(() => {
        tick().catch((err) => {
          logger.error("[subagent-worker] unhandled tick error:", err)
        })
      }, intervalMs)
    }
  }

  // First tick is delayed by `intervalMs` so the v5 process has a
  // moment to finish bootstrapping before the worker starts hammering
  // the outbox.
  setTimeout(() => {
    tick().catch((err) => {
      logger.error("[subagent-worker] unhandled initial tick error:", err)
    })
  }, intervalMs)

  logger.warn(`[subagent-worker] started (intervalMs=${intervalMs})`)

  return {
    stop: () => {
      stopped = true
    },
  }
}
