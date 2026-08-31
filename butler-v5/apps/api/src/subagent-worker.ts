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
import type { EventBridge } from "@butler/persistence/event-bridge.js"
import type { OutboxMessage } from "@butler/persistence/outbox.js"
import { type LLMAdapter, type LLMMessage, type LLMTool } from "@butler/adapters"
import { ALLOWED_CAPABILITIES } from "@butler/runtime/delegate-runtime.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { AgentKernel } from "@butler/runtime/agent-kernel.js"
import { RunPauseForApproval } from "@butler/runtime/run-engine.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import {
  computeCostUsd,
  parseLlmPricing,
  resolveCurrentLlmModel,
} from "./llm-pricing.js"
import type { ModelDecision } from "@butler/runtime/decision.js"
import {
  runConversationLoop,
  type ConversationLoopLlmTool,
  type ConversationLoopLogger,
  type ConversationLoopMessage,
  type ConversationLoopPorts,
} from "@butler/runtime/execution/index.js"
import type { EventStorePort } from "@butler/ports/core/event-store.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { pushEventToSubscribers } from "./ws-routes.js"
import { writeSubagentAudit } from "./audit-service.js"
import { notifySubagentCompletion } from "./wechat-run-notify.js"
import {
  isToolCallAllowed,
  llmToolsForCapabilities,
  normalizeCapabilityNames,
} from "./capability-guard.js"
import { findTool, makeWeibutlerTools } from "./tools.js"
import { makeToolExecutor, resolveOwnerSubject, toolTimeoutMs } from "./tool-boundary.js"
import { toRunResult, isPendingApprovalOutcome } from "./approval-resume.js"
import { ensureDelegationToolGrants } from "./delegation-grants.js"
import { enrichSubagentDevReply } from "./dev-quality-gate.js"
import { execModelTrace } from "@butler/adapters"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
import { recordChildRunStatus } from "./project-state.js"
import { resolveWechatUserFromConversation } from "./wechat-run-notify.js"

/**
 * D8-arch-align §20 #11: a no-op EventStorePort used to satisfy
 * `AgentKernel`'s bridge contract. The canonical subagent reply
 * (and the per-tool-call audit) is written through the explicit
 * `bridge.appendConversationEvent(...)` and `writeSubagentAudit(...)`
 * paths in `handleOutboxMessage` / `executeTool` port — the kernel's
 * own write is intentionally suppressed because the worker is the
 * sole writer of the parent's `AssistantMessageProduced` event for
 * a delegated child turn.
 */
const noopEventStorePort: EventStorePort = {
  appendConversationEvent: async () => undefined,
  appendConversationEventWithOutbox: async () => "",
}

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

async function markChildRunRunning(store: RuntimeStore, childRunId: string): Promise<void> {
  const run = await store.getRun(childRunId)
  if (!run || run.status !== "queued") return
  await store.transitionRunStatus(run.id, run.version, "running", new Date())
}

async function finalizeChildRun(
  store: RuntimeStore,
  childRunId: string,
  outcome: { readonly ok: boolean; readonly reply: string; readonly role: string },
): Promise<void> {
  const run = await store.getRun(childRunId)
  if (!run) return
  if (run.status !== "queued" && run.status !== "running") return
  const now = new Date()
  let current = run
  if (current.status === "queued") {
    current = await store.transitionRunStatus(current.id, current.version, "running", now)
  }
  const stepId = crypto.randomUUID()
  await store.createStep({
    id: stepId,
    runId: current.id,
    kind: "result",
    status: outcome.ok ? "succeeded" : "failed",
    input: { role: outcome.role },
    createdAt: now,
  })
  await store.updateStep({
    stepId,
    output: { reply: outcome.reply.slice(0, 2000) },
    updatedAt: now,
  })
  const fresh = await store.getRun(current.id)
  if (!fresh || (fresh.status !== "queued" && fresh.status !== "running")) return
  await store.transitionRunStatus(
    fresh.id,
    fresh.version,
    outcome.ok ? "succeeded" : "failed",
    new Date(),
  )
}

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
  env: NodeJS.ProcessEnv,
  runtimeStore?: RuntimeStore,
  childRunId?: string | null,
): Promise<{ readonly content: string; readonly waitingApproval?: boolean }> {
  const ownerSubject = resolveOwnerSubject(env, parentConversationId)
  if (runtimeStore && childRunId) {
    try {
      await ensureDelegationToolGrants({
        store: runtimeStore,
        childRunId,
        ownerSubject,
        capabilities,
        maxUses: MAX_CHILD_ITERATIONS,
        env,
      })
    } catch {
      // Grant pre-issue is best-effort; tool boundary still enforces policy.
    }
  }
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
    env,
    runtimeStore,
    runId: childRunId ?? undefined,
    workspaceRoot: (env["BUTLER_V5_WORKSPACE_ROOT"] ?? "").trim() || undefined,
  })
  const toolExecutor = makeToolExecutor({
    tools: runtimeTools,
    store: runtimeStore,
    runId: childRunId ?? undefined,
    ownerSubject,
    subject: ownerSubject,
    // The child run record is created with conversationId = childConversationId
    // (delegate-runtime). A run_command that asks approval must carry the SAME
    // conversationId on its waiting_approval step, otherwise resumeRun on approve
    // rejects the mismatch ("belongs to child-..., not parent..."). The child's
    // tools still read the parent stream (runtimeTools above uses parentConversationId).
    conversationId: childConversationId,
    timeoutMsFor: toolTimeoutMs,
  })

  // D8-arch-align §20 #11: reuse the canonical conversation loop instead of
  // a hand-rolled for-loop. Subagent-specific concerns (capability allowlist,
  // per-tool-call audit, owner-approval pause) live in the ports below; the
  // loop body, decoder feedback, stuck-loop detection, and LLM-timeout stay
  // shared with the main conversation.
  const loopLogger: ConversationLoopLogger = {
    warn: (msg, extra) => {
      // eslint-disable-next-line no-console -- operator log mirror
      console.warn(`[subagent:loop] ${msg}`, extra ?? "")
    },
    error: (msg, err) => {
      // eslint-disable-next-line no-console -- operator log mirror
      console.error(`[subagent:loop] ${msg}`, err)
    },
  }
  const ports: ConversationLoopPorts = {
    logger: loopLogger,
    complete: async (msgs, tools) => {
      const llmStartedAt = Date.now()
      // D24: pricing lookup is best-effort; missing pricing leaves
      // costUsd as null (aligned with the field's "unknown" semantics).
      const pricing = parseLlmPricing(env)
      const currentModel = resolveCurrentLlmModel(env)
      try {
        // ConversationLoopLlmTool is structurally a subset of LLMTool
        // (name required; description + parameters optional on the loop side,
        // required on the adapter side). The downcast is safe because the
        // adapter fills any missing description/parameters from its defaults.
        const opts =
          tools.length > 0
            ? { tools: tools as unknown as readonly LLMTool[] }
            : undefined
        const resp = await Effect.runPromise(
          adapter.complete(msgs as unknown as readonly LLMMessage[], opts).pipe(
            Effect.timeout(LLM_TIMEOUT_MS),
          ),
        )
        // D23: emit llm_call step trace with token usage.
        // D24: fills costUsd when env-driven pricing is available.
        const costUsd =
          resp.usage !== undefined && currentModel !== null
            ? computeCostUsd(resp.usage, currentModel, pricing)
            : null
        getSharedLocalTracer().record({
          kind: "step",
          name: "llm_call",
          status: "ok",
          conversationId: childConversationId,
          runId: childRunId ?? null,
          subject: ownerSubject,
          durationMs: Date.now() - llmStartedAt,
          ...(resp.usage !== undefined ? { token: resp.usage } : {}),
          costUsd,
        })
        return {
          ok: true as const,
          response: {
            content: resp.content,
            toolCalls: resp.toolCalls,
            ...(resp.usage !== undefined ? { usage: resp.usage } : {}),
          },
        }
      } catch (err) {
        // D23: error trace (no usage when the call never reached the model).
        getSharedLocalTracer().record({
          kind: "step",
          name: "llm_call",
          status: "error",
          conversationId: childConversationId,
          runId: childRunId ?? null,
          subject: ownerSubject,
          durationMs: Date.now() - llmStartedAt,
          detail: { reason: err instanceof Error ? err.message : String(err) },
        })
        return {
          ok: false as const,
          reason: err instanceof Error ? err.message : String(err),
        }
      }
    },
    findTool: (name: string) => findTool(runtimeTools, name),
    executeTool: async (def: ToolDefinition, args: Readonly<Record<string, unknown>>) => {
      if (!isToolCallAllowed(def.name, capabilities)) {
        const reason = `capability denied: ${def.name}`
        writeSubagentAudit(runtimeStore, {
          ts: new Date().toISOString(),
          kind: "rejection",
          parentConversationId,
          childConversationId,
          role,
          task,
          capabilities,
          reason,
          toolName: def.name,
        })
        return { ok: false, reason }
      }
      const rawOutcome = await toolExecutor.execute(def, args as Record<string, unknown>)
      if (isPendingApprovalOutcome(rawOutcome)) {
        const stepId = rawOutcome.pendingApproval.stepId
        writeSubagentAudit(runtimeStore, {
          ts: new Date().toISOString(),
          kind: "tool_call",
          parentConversationId,
          childConversationId,
          role,
          task,
          capabilities,
          toolName: def.name,
          reason: rawOutcome.reason,
        })
        throw new RunPauseForApproval({
          reply: `${rawOutcome.reason}\n审批编号: ${stepId}\n需出网命令请 Owner 执行：butler approve ${stepId} --network-allowlist registry.npmjs.org:443`,
          iterations: 0,
          toolCalls: 0,
          finalDecision: "WaitForApproval" as ModelDecision["_tag"],
          traces: [`waiting approval ${stepId} for ${def.name}`],
        })
      }
      const toolResult = toRunResult(rawOutcome)
      writeSubagentAudit(runtimeStore, {
        ts: new Date().toISOString(),
        kind: "tool_call",
        parentConversationId,
        childConversationId,
        role,
        task,
        capabilities,
        toolName: def.name,
        reason: toolResult.ok ? "ok" : toolResult.reason,
      })
      return toolResult
    },
    stubReply: () => `（子代理 ${role} 调用失败）`,
  }
  // Kernel is required by runConversationLoop but its bridge writes are
  // intentionally suppressed: subagent owns the parent-stream AssistantMessage
  // Produced write itself (see handleOutboxMessage below).
  const kernel = new AgentKernel({
    bridge: noopEventStorePort,
    conversationId: childConversationId,
    projectId: "subagent",
    actor: { kind: "agent", id: `subagent-${role}` },
  })

  try {
    const loopResult = await runConversationLoop({
      kernel,
      messages: messages as unknown as ConversationLoopMessage[],
      llmTools: advertised as unknown as readonly ConversationLoopLlmTool[],
      ports,
      maxIterations: MAX_CHILD_ITERATIONS,
      llmTimeoutMs: LLM_TIMEOUT_MS,
    })
    return { content: loopResult.reply }
  } catch (err) {
    if (err instanceof RunPauseForApproval) {
      const payload =
        typeof err.payload === "object" && err.payload !== null
          ? (err.payload as { reply?: unknown })
          : null
      const reply =
        payload && typeof payload.reply === "string"
          ? payload.reply
          : `（子代理 ${role} 需要审批）`
      return { content: reply, waitingApproval: true }
    }
    throw err
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
  runtimeStore: RuntimeStore | undefined,
  env: NodeJS.ProcessEnv,
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
  logger.warn(`[subagent-worker] ${execModelTrace(env)}`)
  const payload = msg.payload as {
    childConversationId?: unknown
    role?: unknown
    task?: unknown
    capabilities?: unknown
    childRunId?: unknown
    parentRunId?: unknown
    notifySubject?: unknown
  }
  const childConversationId =
    typeof payload.childConversationId === "string" ? payload.childConversationId : ""
  const role = typeof payload.role === "string" && payload.role.trim() ? payload.role : "general"
  const task = typeof payload.task === "string" ? payload.task : ""
  const capabilities = normalizeCapabilityNames(payload.capabilities)
  const childRunId = typeof payload.childRunId === "string" ? payload.childRunId : null
  const notifySubject =
    typeof payload.notifySubject === "string" ? payload.notifySubject.trim() : ""
  if (!childConversationId || !task) {
    logger.warn(
      `[subagent-worker] outbox msg ${msg.messageId} missing childConversationId or task; skipping`,
    )
    return
  }
  if (runtimeStore && childRunId) {
    try {
      await markChildRunRunning(runtimeStore, childRunId)
      if (notifySubject) {
        recordChildRunStatus({
          userId: notifySubject,
          projectId: getWechatActiveProjectId(notifySubject, env),
          childRunId,
          status: "running",
          env,
        })
      }
    } catch (err) {
      logger.warn(
        `[subagent-worker] failed to mark child run running ${childRunId}: ${
          err instanceof Error ? err.message : String(err)
        }`,
      )
    }
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
    const stubContent = "（子代理未配置 LLM，无法执行）"
    const stubEvent = {
      streamId: msg.streamId,
      eventId: `evt-${Date.now()}-subagent-stub`,
      eventType: "AssistantMessageProduced" as const,
      correlationId: `corr-${Date.now()}-subagent`,
      actor: { kind: "agent" as const, id: `subagent-${role}` },
      event: {
        _tag: "AssistantMessageProduced" as const,
        content: prefixReply(role, stubContent),
      },
    }
    await bridge.appendConversationEvent(stubEvent)
    if (runtimeStore && childRunId) {
      try {
        await finalizeChildRun(runtimeStore, childRunId, {
          ok: false,
          reply: stubContent,
          role,
        })
      } catch (err) {
        logger.warn(
          `[subagent-worker] failed to finalize child run ${childRunId}: ${
            err instanceof Error ? err.message : String(err)
          }`,
        )
      }
    }
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
  let result: { readonly content: string; readonly waitingApproval?: boolean }
  let llmOk = true
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
      env,
      runtimeStore,
      childRunId,
    )
    logger.warn(`[subagent-worker] LLM replied: ${result.content.slice(0, 80)}`)
  } catch (err) {
    logger.error(`[subagent-worker] child LLM call failed for child ${childConversationId}:`, err)
    llmOk = false
    result = {
      content: `（子代理 ${role} 调用失败: ${err instanceof Error ? err.message : String(err)}）`,
    }
  }
  const notifyUser =
    notifySubject || (await resolveWechatUserFromConversation(bridge, msg.streamId)) || ""
  const inboundProject = notifyUser ? getWechatActiveProjectId(notifyUser, env) : "wechat"
  let replyBody = result.content
  try {
    replyBody = await enrichSubagentDevReply({
      projectId: inboundProject,
      fromUserId: notifyUser || "subagent",
      capabilities,
      ok: llmOk,
      baseReply: result.content,
      env,
    })
  } catch (err) {
    logger.warn(
      `[subagent-worker] dev verify enrichment failed: ${
        err instanceof Error ? err.message : String(err)
      }`,
    )
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
        content: prefixReply(role, replyBody),
      },
    }
    await bridge.appendConversationEvent(replyEvent)
    if (runtimeStore && childRunId) {
      try {
        const childRun = await runtimeStore.getRun(childRunId)
        const waitingApproval =
          result.waitingApproval === true || childRun?.status === "waiting_approval"
        if (!waitingApproval) {
          await finalizeChildRun(runtimeStore, childRunId, {
            ok: llmOk,
            reply: replyBody,
            role,
          })
        }
        if (notifySubject) {
          recordChildRunStatus({
            userId: notifySubject,
            projectId: getWechatActiveProjectId(notifySubject, env),
            childRunId,
            status: waitingApproval ? "running" : llmOk ? "succeeded" : "failed",
            env,
          })
        }
      } catch (err) {
        logger.warn(
          `[subagent-worker] failed to finalize child run ${childRunId}: ${
            err instanceof Error ? err.message : String(err)
          }`,
        )
      }
    }
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
      replyExcerpt: replyBody.slice(0, 200),
    })
    // R8.x.8: push the reply to any WS clients subscribed to the
    // parent conversation. pushEventToSubscribers is a no-op when
    // nobody is listening, so this is safe to call unconditionally.
    pushEventToSubscribers(msg.streamId, {
      eventType: replyEvent.eventType,
      event: replyEvent.event,
      eventId: replyEvent.eventId,
    })
    await notifySubagentCompletion({
      bridge,
      parentConversationId: msg.streamId,
      ...(notifySubject ? { notifySubject } : {}),
      role,
      task,
      reply: replyBody,
      ok: llmOk,
      env,
    }).catch((err) => {
      logger.warn(
        `[subagent-worker] run notify failed: ${err instanceof Error ? err.message : String(err)}`,
      )
    })
  } catch (err) {
    logger.error(`[subagent-worker] failed to append reply to parent ${msg.streamId}:`, err)
    if (runtimeStore && childRunId) {
      try {
        await finalizeChildRun(runtimeStore, childRunId, {
          ok: false,
          reply: err instanceof Error ? err.message : String(err),
          role,
        })
      } catch {
        // best-effort
      }
    }
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
  const intervalMs =
    Number(env["BUTLER_V5_SUBAGENT_WORKER_INTERVAL_MS"] ?? "") ||
    opts.intervalMs ||
    POLL_INTERVAL_MS
  const runtimeStore = opts.runtimeStore
  let stopped = false

  const tick = async (): Promise<void> => {
    if (stopped) return
    try {
      const adapter = pickProvider(env)
      const delivered = await bridge.runWorker(async (msg) => {
        await handleOutboxMessage(bridge, adapter, msg, logger, runtimeStore, env)
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
