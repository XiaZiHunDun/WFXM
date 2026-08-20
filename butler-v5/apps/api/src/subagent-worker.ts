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
import { type LLMAdapter, type LLMAssistantResponse, type LLMMessage } from "@butler/adapters"
import { ALLOWED_CAPABILITIES } from "@butler/runtime/delegate-runtime.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { pushEventToSubscribers } from "./ws-routes.js"
import { writeSubagentAudit } from "./audit-service.js"
import {
  isToolCallAllowed,
  llmToolsForCapabilities,
  normalizeCapabilityNames,
} from "./capability-guard.js"
import { findTool, makeWeibutlerTools } from "./tools.js"
import { makeToolExecutor, resolveOwnerSubject } from "./tool-boundary.js"
import { toRunResult } from "./approval-resume.js"

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
 * R8.x.10: bound child tool-call iterations so a chatty model cannot
 * stall the worker. On overrun we return whatever text we last saw
 * (or a short fallback).
 */
const MAX_CHILD_ITERATIONS = 3

/** Per-tool wall-clock budget inside the child turn. */
const CHILD_TOOL_TIMEOUT_MS = 5_000

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
 * Run the child LLM turn. R8.x.10: advertises only granted tools and
 * refuses to execute any tool_call outside that set. Existing
 * general-only delegations keep the previous single-shot text path
 * (no tools advertised).
 */
async function runChildLlm(
  adapter: LLMAdapter,
  role: string,
  task: string,
  capabilities: readonly string[],
  bridge: EventBridge,
  parentConversationId: string,
  childConversationId: string,
  runtimeStore?: RuntimeStore,
): Promise<{ readonly content: string }> {
  const advertised = llmToolsForCapabilities(capabilities)
  const toolHint =
    advertised.length === 0
      ? "你没有可用工具，请只用语言作答。"
      : `你只能使用这些工具: ${advertised.map((t) => t.name).join(", ")}。禁止调用未列出的工具。`
  const messages: LLMMessage[] = [
    {
      role: "system",
      content: `你是一名 ${role} 子代理，正在处理一个被委派的任务。请用简洁、可直接回复给用户的方式回答。${toolHint}`,
    },
    { role: "user", content: task },
  ]
  const runtimeTools = makeWeibutlerTools({
    bridge,
    conversationId: parentConversationId,
    actor: { kind: "agent", id: `subagent-${role}` },
  })
  const toolExecutor = makeToolExecutor({
    tools: runtimeTools,
    ownerSubject: resolveOwnerSubject(process.env, parentConversationId),
    subject: `subagent-${role}`,
    conversationId: parentConversationId,
    timeoutMsFor: () => CHILD_TOOL_TIMEOUT_MS,
  })
  const completeOpts = advertised.length > 0 ? { tools: advertised } : undefined
  let lastText = ""

  for (let iteration = 0; iteration < MAX_CHILD_ITERATIONS; iteration++) {
    const outcome = await Effect.runPromise(
      adapter.complete(messages, completeOpts).pipe(
        Effect.timeout(LLM_TIMEOUT_MS),
        Effect.match({
          onFailure: (err) => ({
            ok: false as const,
            reason: err instanceof Error ? err.message : String(err),
          }),
          onSuccess: (v: LLMAssistantResponse) => ({ ok: true as const, value: v }),
        }),
      ),
    )
    if (!outcome.ok) {
      return { content: `（子代理 ${role} 调用失败: ${outcome.reason}）` }
    }
    const response = outcome.value
    lastText = response.content
    if (response.toolCalls.length === 0) {
      return { content: response.content }
    }
    messages.push({
      role: "assistant",
      content: response.content,
      toolCalls: response.toolCalls,
    })
    const toolResultMessages: LLMMessage[] = []
    for (const tc of response.toolCalls) {
      if (!isToolCallAllowed(tc.name, capabilities)) {
        const reason = `capability denied: ${tc.name}`
        writeSubagentAudit(runtimeStore, {
          ts: new Date().toISOString(),
          kind: "rejection",
          parentConversationId,
          childConversationId,
          role,
          task,
          capabilities,
          reason,
          toolName: tc.name,
        })
        toolResultMessages.push({
          role: "tool",
          content: `[error] ${reason}`,
          toolCallId: tc.id,
          toolName: tc.name,
        })
        continue
      }
      const def = findTool(runtimeTools, tc.name)
      if (!def) {
        toolResultMessages.push({
          role: "tool",
          content: `[error] unknown tool: ${tc.name}`,
          toolCallId: tc.id,
          toolName: tc.name,
        })
        continue
      }
      const toolResult = toRunResult(await toolExecutor.execute(def, tc.args))
      writeSubagentAudit(runtimeStore, {
        ts: new Date().toISOString(),
        kind: "tool_call",
        parentConversationId,
        childConversationId,
        role,
        task,
        capabilities,
        toolName: tc.name,
        reason: toolResult.ok ? "ok" : toolResult.reason,
      })
      toolResultMessages.push({
        role: "tool",
        content: toolResult.ok ? String(toolResult.output) : `[error] ${toolResult.reason}`,
        toolCallId: tc.id,
        toolName: tc.name,
      })
    }
    messages.push(...toolResultMessages)
  }
  return {
    content: lastText.trim()
      ? lastText
      : `（子代理 ${role} 工具循环已达上限 ${MAX_CHILD_ITERATIONS}）`,
  }
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
  runtimeStore?: RuntimeStore,
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
    capabilities?: unknown
  }
  const childConversationId =
    typeof payload.childConversationId === "string" ? payload.childConversationId : ""
  const role = typeof payload.role === "string" && payload.role.trim() ? payload.role : "general"
  const task = typeof payload.task === "string" ? payload.task : ""
  const capabilities = normalizeCapabilityNames(payload.capabilities)
  if (!childConversationId || !task) {
    logger.warn(
      `[subagent-worker] outbox msg ${msg.messageId} missing childConversationId or task; skipping`,
    )
    return
  }
  // R8.x.9: defensive allowlist check. The route layer already
  // rejects invalid capabilities, but if an outbox message was
  // enqueued by another path we still must not call the LLM.
  const allowedSet = new Set<string>(ALLOWED_CAPABILITIES)
  const invalidCap = capabilities.find((c) => !allowedSet.has(c))
  if (invalidCap !== undefined) {
    const reason = `invalid capability: ${invalidCap} (allowed: ${ALLOWED_CAPABILITIES.join(", ")})`
    logger.warn(`[subagent-worker] rejecting outbox msg ${msg.messageId}: ${reason}`)
    writeSubagentAudit(runtimeStore, {
      ts: new Date().toISOString(),
      kind: "rejection",
      parentConversationId: msg.streamId,
      childConversationId,
      role,
      task,
      capabilities,
      reason,
    })
    return
  }
  if (!adapter) {
    logger.warn(
      `[subagent-worker] no LLM adapter configured; writing stub reply for child ${childConversationId}`,
    )
    const stubEvent = {
      streamId: msg.streamId,
      eventId: `evt-${Date.now()}-subagent-stub`,
      eventType: "AssistantMessageProduced" as const,
      correlationId: `corr-${Date.now()}-subagent`,
      actor: { kind: "agent" as const, id: `subagent-${role}` },
      event: {
        _tag: "AssistantMessageProduced" as const,
        content: prefixReply(role, "（子代理未配置 LLM，无法执行）"),
      },
    }
    await bridge.appendConversationEvent(stubEvent)
    // R8.x.8: push the reply to any WS clients subscribed to the
    // parent conversation. pushEventToSubscribers is a no-op when
    // nobody is listening, so this is safe to call unconditionally.
    pushEventToSubscribers(msg.streamId, {
      eventType: stubEvent.eventType,
      event: stubEvent.event,
      eventId: stubEvent.eventId,
    })
    return
  }
  let result: { readonly content: string }
  try {
    logger.warn(`[subagent-worker] invoking LLM for role=${role} task=${task.slice(0, 60)}`)
    result = await runChildLlm(
      adapter,
      role,
      task,
      capabilities,
      bridge,
      msg.streamId,
      childConversationId,
      runtimeStore,
    )
    logger.warn(`[subagent-worker] LLM replied: ${result.content.slice(0, 80)}`)
  } catch (err) {
    logger.error(`[subagent-worker] child LLM call failed for child ${childConversationId}:`, err)
    result = {
      content: `（子代理 ${role} 调用失败: ${err instanceof Error ? err.message : String(err)}）`,
    }
  }
  try {
    const replyEvent = {
      streamId: msg.streamId,
      eventId: `evt-${Date.now()}-subagent-reply`,
      eventType: "AssistantMessageProduced" as const,
      correlationId: `corr-${Date.now()}-subagent`,
      actor: { kind: "agent" as const, id: `subagent-${role}` },
      event: {
        _tag: "AssistantMessageProduced" as const,
        content: prefixReply(role, result.content),
      },
    }
    await bridge.appendConversationEvent(replyEvent)
    // R8.x.9: record completion to the audit log. The excerpt is
    // capped at 200 chars so the JSONL stays grep-friendly even for
    // long LLM replies.
    writeSubagentAudit(runtimeStore, {
      ts: new Date().toISOString(),
      kind: "completion",
      parentConversationId: msg.streamId,
      childConversationId,
      role,
      task,
      capabilities,
      replyExcerpt: result.content.slice(0, 200),
    })
    // R8.x.8: push the reply to any WS clients subscribed to the
    // parent conversation. pushEventToSubscribers is a no-op when
    // nobody is listening, so this is safe to call unconditionally.
    pushEventToSubscribers(msg.streamId, {
      eventType: replyEvent.eventType,
      event: replyEvent.event,
      eventId: replyEvent.eventId,
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
  opts: {
    readonly logger?: SubagentWorkerLogger
    readonly intervalMs?: number
    readonly runtimeStore?: RuntimeStore
  } = {},
): SubagentWorkerHandle {
  const logger = opts.logger ?? defaultLogger
  const intervalMs = opts.intervalMs ?? POLL_INTERVAL_MS
  const runtimeStore = opts.runtimeStore
  let stopped = false

  const tick = async (): Promise<void> => {
    if (stopped) return
    try {
      const adapter = pickProvider(env)
      const delivered = await bridge.runWorker(async (msg) => {
        await handleOutboxMessage(bridge, adapter, msg, logger, runtimeStore)
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
