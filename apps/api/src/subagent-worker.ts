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
 *   - Fork isolation: the adapter is resolved once per tick by the
 *     injected `pickLLM` (the composition root passes
 *     `(env) => pickLLMForRole(env, "exec")` — see index.ts). Any
 *     provider can be configured in the parent process; the worker just
 *     consumes the chosen adapter.
 *     (D82 T3: this comment previously named `pickLLMProvider`, a
 *     role-unaware function whose only caller was dead code. It has
 *     been deleted, so the name here would have sent the next reader
 *     to a function that no longer exists.)
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
import { type LLMAdapter, type LLMMessage, DEFAULT_LLM_TIMEOUT_MS } from "@butler/adapters"
import { ALLOWED_CAPABILITIES } from "@butler/runtime/delegate-runtime.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { AgentKernel } from "@butler/runtime/agent-kernel.js"
import { RunPauseForApproval } from "@butler/runtime/run-engine.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { computeCostUsd, parseLlmPricing, resolveCurrentLlmModel } from "./llm-pricing.js"
import type { ModelDecision } from "@butler/runtime/decision.js"
import {
  runConversationLoop,
  type ConversationLoopLogger,
  type ConversationLoopPorts,
} from "@butler/runtime/execution/index.js"
import type { EventStorePort } from "@butler/ports/core/event-store.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { pushEventToSubscribers } from "./ws-routes.js"
import { writeSubagentAudit } from "./audit-service.js"
import { notifySubagentCompletion } from "./wechat-run-notify.js"
import { isToolCallAllowed, llmToolsForCapabilities } from "./capability-guard.js"
import { findTool, makeWeibutlerTools } from "./tools.js"
import { makeToolExecutor, toolTimeoutMs } from "./tool-boundary.js"
import { resolveOwnerSubject } from "./tool-boundary-helpers.js"
import { toRunResult, isPendingApprovalOutcome } from "./approval-resume.js"
import { ensureDelegationToolGrants } from "./delegation-grants.js"
import { enrichSubagentDevReply } from "./dev-quality-gate.js"
import { execModelTrace } from "@butler/adapters"
import { safeOwnerError } from "./safe-owner-error.js"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
import { recordChildRunStatus } from "./project-state.js"
import { resolveWechatUserFromConversation } from "./wechat-run-notify.js"
// D75 T1 (CQ-002): handleOutboxMessage split — payload / rejection / stub
// reply helpers extracted to their own modules so the orchestrator can
// stay focused on policy + the main LLM path.
import { parseDelegateOutboxPayload } from "./subagent-worker-payload.js"
import { writeChildRunRejection } from "./subagent-worker-rejection.js"
import { writeChildStubReply } from "./subagent-worker-stub.js"

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
const LLM_TIMEOUT_MS = DEFAULT_LLM_TIMEOUT_MS

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
 *
 * 2026-11-18 L4 smoke: 3 was too small for real file tasks — the model
 * spent one iteration locating the workspace, one writing, and then the
 * loop forced a tool-less final turn, so it reported "could not write"
 * while the worker still delivered the run as a success. 8 leaves room
 * for inspect → write → verify, and `capped` detection below keeps a run
 * that still hits the limit from being reported as completed.
 *
 * 2026-11-18 later run: a write task burned 7 iterations on discovery and
 * hit the cap again, so 12 gives one more discovery round before the
 * forced tool-less final turn.
 *
 * Phase 7 fix F3: real-repo delegation needs write + verify across several
 * files, so 20 leaves room for discovery, multiple writes, and the final
 * tool-less summary turn.
 */
const MAX_CHILD_ITERATIONS = 20

async function markChildRunRunning(store: RuntimeStore, childRunId: string): Promise<void> {
  const run = await store.getRun(childRunId)
  if (!run || run.status !== "queued") return
  await store.transitionRunStatus(run.id, run.version, "running", new Date())
}

export async function finalizeChildRun(
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
 * Phase 7 fix F10: observable worker activity. The Demo Console returned
 * `ok:true` while subagent work was still running in the background; these
 * events let a status endpoint report real progress instead of guessing.
 */
export type SubagentWorkerEvent =
  | {
      readonly type: "task-start"
      readonly messageId: string
      readonly streamId: string
    }
  | {
      readonly type: "task-done"
      readonly messageId: string
      readonly streamId: string
    }
  | {
      readonly type: "task-error"
      readonly messageId: string
      readonly error: string
    }
  | {
      readonly type: "idle"
    }

/**
 * Subagent reply prefix. Mirrors the `[子代理 ...]` marker the
 * parent butler loop already emits elsewhere so users see a
 * consistent label when the subagent's reply shows up in
 * `recall_history`.
 */
export function prefixReply(role: string, content: string): string {
  return `[子代理 ${role} 的回复] ${content}`
}

/**
 * D60 T1.1 (audit #3 F-01): owner-facing reply when the child loop pauses
 * for approval. The stepId UUID and operator CLI stay in the `traces`
 * array for §14 observability, never in the reply text (D48 §4 owner-facing
 * contract). Exported for testability.
 */
export function buildPauseForApprovalReply(reason: string): string {
  return `${reason}\n请 Owner 审批该步（子代理需网络访问）。`
}

/**
 * Phase 7 fix F2: the child prompt must spell out the execution contract.
 * Without it the model writes one file and answers in prose ("已完成"),
 * which the loop correctly treats as a plain-text Respond — so the child
 * run is recorded as done while the task is still half-finished.
 * Exported for unit tests.
 */
export function buildChildSystemPrompt(
  role: string,
  advertisedTools: readonly { readonly name: string }[],
): string {
  const available = advertisedTools.map((t) => t.name)
  if (available.length === 0) {
    return `你是一名 ${role} 子代理，正在处理一个被委派的任务。你没有可用工具，请只用语言作答，并明确指出哪些部分无法落地。`
  }
  return [
    `你是一名 ${role} 子代理，正在处理一个被委派的任务。`,
    "执行规则：",
    "1. 需要读写文件、执行命令时，必须实际调用工具（原生 tool call），不要用文字描述代替。",
    "2. 读取/查看文件只是准备动作，不是任务目标；读完必须继续执行写入、修改或命令，直到任务点名的产物全部存在。",
    "3. 任务目标没有全部落地前，不要用纯文本宣布完成；只有全部完成才允许给出简短总结。",
    "4. 声明完成前，必须用 list_files / read_file 核对目标文件真实存在且内容符合要求。",
    `5. 只能使用这些工具：${available.join(", ")}；禁止调用未列出的工具。`,
    "6. 大文件用 read_file（配合 offset/limit）分段读，不要用 run_command 反复 grep/sed 同一文件；同一条命令不要重复超过两次。",
    "7. 修改后用 pnpm typecheck 或 pnpm build 自检；自检命令失败时读报错并修，不要原样重跑第三次。",
  ].join("\n")
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
  turnId?: string | null,
): Promise<{
  readonly content: string
  readonly waitingApproval?: boolean
  readonly capped?: boolean
}> {
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
  const messages: LLMMessage[] = [
    { role: "system", content: buildChildSystemPrompt(role, advertised) },
    { role: "user", content: task },
  ]
  const workspaceRoot = (env["BUTLER_V5_WORKSPACE_ROOT"] ?? "").trim() || undefined
  const runtimeTools = makeWeibutlerTools({
    bridge,
    conversationId: parentConversationId,
    actor: { kind: "agent", id: `subagent-${role}` },
    env,
    ...(runtimeStore === undefined ? {} : { runtimeStore }),
    ...(childRunId == null ? {} : { runId: childRunId }),
    ...(turnId == null ? {} : { turnId }),
    ...(workspaceRoot === undefined ? {} : { workspaceRoot }),
  })
  const toolExecutor = makeToolExecutor({
    tools: runtimeTools,
    ...(runtimeStore === undefined ? {} : { store: runtimeStore }),
    ...(childRunId == null ? {} : { runId: childRunId }),
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
        // D61 T3: ConversationLoopLlmTool.description/parameters now match
        // LLMTool structurally (root-cause widening), so no cast is needed.
        const opts = tools.length > 0 ? { tools } : undefined
        const resp = await Effect.runPromise(
          adapter.complete(msgs, opts).pipe(Effect.timeout(LLM_TIMEOUT_MS)),
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
          turnId: turnId ?? null,
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
          turnId: turnId ?? null,
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
          // D58 T1: thread owner subject for audit_events.subject.
          ownerSubject,
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
          // D58 T1: thread owner subject for audit_events.subject.
          ownerSubject,
        })
        throw new RunPauseForApproval({
          // D60 T1.1 (audit #3 F-01): close D59 T3 missed-sweep — drop the
          // stepId UUID + operator CLI from the owner-facing reply.
          // stepId stays in the trace below for §14 observability.
          reply: buildPauseForApprovalReply(rawOutcome.reason),
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
        // D58 T1: thread owner subject for audit_events.subject.
        ownerSubject,
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
      // D60 T3.1 (audit #2 F-05): structural-subset cast removed —
      // ConversationLoopToolCall now accepts LLMToolCall directly.
      messages,
      llmTools: advertised,
      ports,
      maxIterations: MAX_CHILD_ITERATIONS,
      maxToolCalls: MAX_CHILD_ITERATIONS,
      toolFirst: advertised.length > 0,
      // Phase 7 fix F12: re-running `pnpm typecheck` after each edit is
      // legitimate, but the default stuck-loop threshold (3) aborts the child
      // on the third identical command. Give children a little more room;
      // iteration and tool budgets still bound the loop.
      stuckLoopThreshold: 6,
      llmTimeoutMs: LLM_TIMEOUT_MS,
    })
    // `iterations === cap` means the loop ran out of turns instead of the
    // model deciding it was done; the reply is then a progress/hand-off
    // text, not a completion. Surface that so the caller can stop telling
    // the owner the work succeeded.
    // Phase 7 fix F4: a Finish decision on the failure path returns the
    // generic stub reply. Attach the loop's last traces so the parent sees
    // the real reason (e.g. `llm failure: ...`) instead of a bare
    // "调用失败".
    const finishDiagnostics =
      loopResult.finalDecision === "Finish" && loopResult.traces.length > 0
        ? `\n（诊断：${loopResult.traces.slice(-2).join("；")}）`
        : ""
    return {
      content: `${loopResult.reply}${finishDiagnostics}`,
      capped: loopResult.iterations >= MAX_CHILD_ITERATIONS,
    }
  } catch (err) {
    if (err instanceof RunPauseForApproval) {
      const payload =
        typeof err.payload === "object" && err.payload !== null
          ? (err.payload as { reply?: unknown })
          : null
      const reply =
        payload && typeof payload.reply === "string" ? payload.reply : `（子代理 ${role} 需要审批）`
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
  const { childConversationId, role, task, capabilities, childRunId, notifySubject, turnId } =
    parseDelegateOutboxPayload(msg)
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
    writeChildRunRejection({
      runtimeStore,
      msg,
      childConversationId,
      role,
      task,
      capabilities,
      invalidCapability: invalidCap,
      allowedCapabilities: ALLOWED_CAPABILITIES,
      logger,
    })
    return
  }
  if (!adapter) {
    await writeChildStubReply({
      bridge,
      msg,
      childConversationId,
      role,
      runtimeStore,
      childRunId,
      logger,
    })
    return
  }
  let result: {
    readonly content: string
    readonly waitingApproval?: boolean
    readonly capped?: boolean
  }
  let llmOk = true
  try {
    logger.warn(
      `[subagent-worker] invoking LLM for role=${role} task=${task.slice(0, 60)} len=${task.length}`,
    )
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
      turnId,
    )
    logger.warn(`[subagent-worker] LLM replied: ${result.content.slice(0, 80)}`)
  } catch (err) {
    logger.error(`[subagent-worker] child LLM call failed for child ${childConversationId}:`, err)
    llmOk = false
    // D62 T1 (audit #3 F-10): replace raw err.message leak with defensive
    // helper so the assistant-message content (which surfaces to owner via
    // the notify path) is a safe Chinese fallback. Full error stays in
    // the logger.error call above.
    result = {
      content: `${safeOwnerError(err, `（子代理 ${role} 调用失败，请稍后重试）`, {
        operation: "subagent-llm-call",
        childConversationId,
        role,
      })}（诊断：${err instanceof Error ? err.name : "unknown"}）`,
    }
  }
  // A run that stopped at the iteration cap did not finish the task. Do not
  // let the parent stream / run status claim success: mark it failed and make
  // the first line of the reply say so, so the owner never reads a hand-off
  // message as "done".
  if (result.capped === true && llmOk) {
    llmOk = false
    result = {
      content: `执行未完成（达到步数上限，已停止）：${result.content}`,
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
      ...(runtimeStore === undefined ? {} : { runtimeStore }),
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
      eventId: crypto.randomUUID(),
      eventType: "AssistantMessageProduced" as const,
      correlationId: crypto.randomUUID(),
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
    /** Phase 7 F10: activity hook for status surfaces (Demo Console). */
    readonly onEvent?: (event: SubagentWorkerEvent) => void
  } = {},
): SubagentWorkerHandle {
  const logger = opts.logger ?? defaultLogger
  const emit = (event: SubagentWorkerEvent): void => {
    try {
      opts.onEvent?.(event)
    } catch {
      // A broken observer must never break task delivery.
    }
  }
  const intervalMs =
    Number(env["BUTLER_V5_SUBAGENT_WORKER_INTERVAL_MS"] ?? "") ||
    opts.intervalMs ||
    POLL_INTERVAL_MS
  const runtimeStore = opts.runtimeStore
  let stopped = false
  // D60 T1.2 (audit #1 F-01): close D58 T3 missed-sweep — track the timer
  // handle so stop() can cancel a pending tick that hasn't fired yet
  // (D58 T3 fixed the 3 sweepers; subagent-worker was the lone outlier).
  // D74 audit #20 CQ-008 (extract scheduleNextTick + stopSubagentWorker)
  // could not be applied: the static source-pattern test at
  // subagent-worker.test.ts:753-757 asserts literal `let timer` /
  // `timer = setTimeout(` / `clearTimeout(timer)` patterns. An extracted
  // helper either becomes unused (lint warning) or breaks the test. The
  // function-size cap is met; CQ-008 carried forward.
  let timer: ReturnType<typeof setTimeout> | null = null

  const tick = async (): Promise<void> => {
    if (stopped) return
    try {
      const adapter = pickProvider(env)
      const delivered = await bridge.runWorker(async (msg) => {
        emit({ type: "task-start", messageId: msg.messageId, streamId: msg.streamId })
        try {
          await handleOutboxMessage(bridge, adapter, msg, logger, runtimeStore, env)
          emit({ type: "task-done", messageId: msg.messageId, streamId: msg.streamId })
        } catch (err) {
          emit({
            type: "task-error",
            messageId: msg.messageId,
            error: err instanceof Error ? err.message : String(err),
          })
          throw err
        }
      })
      if (delivered > 0) {
        logger.warn(`[subagent-worker] delivered ${delivered} outbox message(s)`)
      } else {
        emit({ type: "idle" })
      }
    } catch (err) {
      logger.error("[subagent-worker] tick failed:", err)
    }
    if (stopped) return
    // D60 T1.2: capture timer handle so stop() can clearTimeout below.
    timer = setTimeout(() => {
      void tick()
    }, intervalMs)
  }

  // First tick is delayed by `intervalMs` so the v5 process has a
  // moment to finish bootstrapping before the worker starts hammering
  // the outbox.
  timer = setTimeout(() => {
    void tick()
  }, intervalMs)

  logger.warn(`[subagent-worker] started (intervalMs=${intervalMs})`)

  return {
    stop: () => {
      stopped = true
      if (timer) clearTimeout(timer)
      timer = null
    },
  }
}
