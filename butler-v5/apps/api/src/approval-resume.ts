import type { RunTrigger } from "@butler/domain/runtime.js"
import {
  parsePendingCapabilityInput,
  type ApprovalDecision,
} from "@butler/runtime/approval-runtime.js"
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { AgentKernel } from "@butler/runtime/agent-kernel.js"
import {
  DEFAULT_MAX_LOOP_ITERATIONS,
  runConversationLoop,
  type ConversationLoopResult,
} from "@butler/runtime/execution/index.js"
import { RunPauseForApproval } from "@butler/runtime/run-engine.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import type { ToolExecutionOutcome } from "@butler/runtime/capability-boundary.js"
import {
  computeCostUsd,
  parseLlmPricing,
  resolveCurrentLlmModel,
} from "./llm-pricing.js"
import type { RunResult } from "@butler/runtime/tool-runtime.js"
import { Effect } from "effect"
import { pickLLMForRole, type LLMMessage, type LLMTool } from "@butler/adapters"
import { findTool, llmToolsForButler, makeWeibutlerTools } from "./tools.js"
import { makeToolExecutor, resolveOwnerSubject, toolTimeoutMs } from "./tool-boundary.js"
import { stubReply } from "./wechat-inbound-llm.js"
import { isExecCapability } from "./wechat-tool-profile.js"
import type { Wiring } from "./wiring.js"

export { approveWaitingStep, denyWaitingStep } from "@butler/runtime/approval-runtime.js"

export async function markGrantConsumed(
  store: RuntimeStore,
  grant: ScopedGrantRecord,
): Promise<void> {
  if (grant.remainingUses === null) return
  await store.updateScopedGrantRemainingUses(grant.id, Math.max(0, grant.remainingUses - 1))
}

export function isPendingApprovalOutcome(
  outcome: ToolExecutionOutcome,
): outcome is Extract<ToolExecutionOutcome, { pendingApproval: unknown }> {
  return (
    outcome.ok === false &&
    "pendingApproval" in outcome &&
    outcome.pendingApproval !== undefined
  )
}

export function toRunResult(outcome: ToolExecutionOutcome): RunResult {
  if (outcome.ok) return outcome
  return { ok: false, reason: outcome.reason }
}

async function persistCapabilityStep(
  store: RuntimeStore,
  args: {
    readonly runId: string
    readonly capability: string
    readonly toolArgs: Readonly<Record<string, unknown>>
    readonly approvalStepId: string
    readonly grantId: string
    readonly result: RunResult
  },
): Promise<void> {
  const now = new Date()
  const stepId = crypto.randomUUID()
  await store.createStep({
    id: stepId,
    runId: args.runId,
    kind: "capability",
    status: args.result.ok ? "succeeded" : "failed",
    input: {
      capability: args.capability,
      args: args.toolArgs,
      approvalStepId: args.approvalStepId,
      grantId: args.grantId,
      resumed: true,
    },
    createdAt: now,
  })
  await store.updateStep({
    stepId,
    output: args.result.ok
      ? { output: String(args.result.output) }
      : { reason: args.result.reason },
    updatedAt: now,
  })
}

function isLoopResult(value: unknown): value is ConversationLoopResult {
  return (
    !!value &&
    typeof value === "object" &&
    "reply" in value &&
    typeof (value as ConversationLoopResult).reply === "string" &&
    !("ok" in value)
  )
}

function formatPostExecReply(capability: string, toolOutput: string): string {
  if (capability === "write_file") {
    return `✅ 文件已写入\n${toolOutput}`
  }
  if (capability === "run_command") {
    return `✅ 命令已执行\n\`\`\`\n${toolOutput.trim()}\n\`\`\``
  }
  return toolOutput
}

function postApprovalLoopEnabled(env: NodeJS.ProcessEnv): boolean {
  const raw = (env["BUTLER_V5_POST_APPROVAL_LOOP"] ?? "").trim().toLowerCase()
  return raw === "1" || raw === "true" || raw === "yes" || raw === "on"
}

/**
 * After the approved capability succeeds, continue with the full multi-turn
 * conversation loop (tools allowed) so resume is not limited to a single
 * phrasing Step.
 */
async function continueLoopAfterCapability(args: {
  readonly wiring: Wiring
  readonly runId: string
  readonly conversationId: string
  readonly subject: string
  readonly capability: string
  readonly toolOutput: string
  readonly env: NodeJS.ProcessEnv
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
}): Promise<string> {
  if (isExecCapability(args.capability) && !postApprovalLoopEnabled(args.env)) {
    const reply = formatPostExecReply(args.capability, args.toolOutput)
    const now = new Date()
    const stepId = crypto.randomUUID()
    await args.wiring.runtimeStore.createStep({
      id: stepId,
      runId: args.runId,
      kind: "result",
      status: "succeeded",
      input: { afterCapability: args.capability, source: "exec_direct" },
      createdAt: now,
    })
    await args.wiring.runtimeStore.updateStep({
      stepId,
      output: { reply },
      updatedAt: now,
    })
    return reply
  }

  const adapter = pickLLMForRole(args.env, "plan")
  if (!adapter) {
    const now = new Date()
    const stepId = crypto.randomUUID()
    await args.wiring.runtimeStore.createStep({
      id: stepId,
      runId: args.runId,
      kind: "result",
      status: "succeeded",
      input: { afterCapability: args.capability, source: "tool_fallback" },
      createdAt: now,
    })
    await args.wiring.runtimeStore.updateStep({
      stepId,
      output: { reply: args.toolOutput },
      updatedAt: now,
    })
    return args.toolOutput
  }
  const kernel = new AgentKernel({
    bridge: args.wiring.eventBridge,
    conversationId: args.conversationId,
    projectId: "approval-resume",
    actor: { kind: "agent", id: "approval-resume" },
  })
  const userContent =
    `已批准并执行 ${args.capability}，结果：\n${args.toolOutput}\n` +
    `请用中文继续完成用户目标；需要时可调用工具。`
  try {
    await kernel.openTurn({ userMessage: { role: "user", content: userContent } })
  } catch {
    return args.toolOutput
  }

  const allTools = makeWeibutlerTools({
    bridge: args.wiring.eventBridge,
    conversationId: args.conversationId,
    actor: { kind: "agent", id: "approval-resume" },
    ...(args.wechatUserId ? { wechatUserId: args.wechatUserId } : {}),
    ...(args.wechatContextToken ? { wechatContextToken: args.wechatContextToken } : {}),
    runtimeStore: args.wiring.runtimeStore,
    runId: args.runId,
    env: args.env,
    mcpBundle: args.wiring.mcp,
  })
  const tools = allTools.filter((t) => !isExecCapability(t.name as string))
  const llmTools = llmToolsForButler({ env: args.env, mcpBundle: args.wiring.mcp }).filter(
    (t) => !isExecCapability(t.name),
  )
  const toolExecutor = makeToolExecutor({
    tools,
    store: args.wiring.runtimeStore,
    runId: args.runId,
    ownerSubject: resolveOwnerSubject(args.env, args.subject),
    subject: args.subject,
    conversationId: args.conversationId,
    timeoutMsFor: toolTimeoutMs,
    ...(args.wechatUserId ? { wechatUserId: args.wechatUserId } : {}),
    mcpServerIdByCapability: args.wiring.mcp.serverIdByCapability,
  })

  const loopResult = await runConversationLoop({
    kernel,
    messages: [
      {
        role: "system",
        content:
          "You are a helpful butler. An Owner-approved capability already ran. " +
          "Continue the task in Chinese. You may call read-only tools; " +
          "do not request run_command or write_file again in this turn.",
      },
      { role: "user", content: userContent },
    ],
    llmTools,
    maxIterations: DEFAULT_MAX_LOOP_ITERATIONS,
    initialTraces: [`post-approval-loop after ${args.capability}`],
    ports: {
      stubReply: () => stubReply(userContent, args.subject, "approval-resume"),
      findTool: (name) => findTool(tools, name),
      persistAssistantReply: async (content) => {
        try {
          await args.wiring.runtimeStore.appendMessage({
            messageId: crypto.randomUUID(),
            conversationId: args.conversationId,
            role: "assistant",
            content: { text: content },
            triggerSource: "api",
            idempotencyKey: `assistant:approval:${args.runId}:${Date.now()}`,
            createdAt: new Date(),
          })
        } catch {
          // non-fatal
        }
      },
      complete: async (msgs, toolsForLlm) => {
        const llmMessages = msgs as unknown as LLMMessage[]
        const llmStartedAt = Date.now()
        // D24: pricing lookup is best-effort; missing pricing leaves
        // costUsd as null (aligned with the field's "unknown" semantics).
        const pricing = parseLlmPricing(args.env)
        const currentModel = resolveCurrentLlmModel(args.env)
        return Effect.runPromise(
          adapter.complete(llmMessages, { tools: toolsForLlm as unknown as readonly LLMTool[] }).pipe(
            Effect.match({
              onFailure: (err) => {
                // D23: error trace (no usage when the call never reached the model).
                getSharedLocalTracer().record({
                  kind: "step",
                  name: "llm_call",
                  status: "error",
                  conversationId: args.conversationId,
                  runId: args.runId,
                  subject: args.subject,
                  durationMs: Date.now() - llmStartedAt,
                  detail: { reason: err instanceof Error ? err.message : String(err) },
                })
                return {
                  ok: false as const,
                  reason: err instanceof Error ? err.message : String(err),
                }
              },
              onSuccess: (resp) => {
                // D23: success trace carries first-class `token`.
                // D24: fills costUsd when env-driven pricing is available.
                const costUsd =
                  resp.usage !== undefined && currentModel !== null
                    ? computeCostUsd(resp.usage, currentModel, pricing)
                    : null
                getSharedLocalTracer().record({
                  kind: "step",
                  name: "llm_call",
                  status: "ok",
                  conversationId: args.conversationId,
                  runId: args.runId,
                  subject: args.subject,
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
              },
            }),
          ),
        )
      },
      executeTool: async (def, toolArgs) => {
        const outcome = await toolExecutor.execute(def, toolArgs)
        if (isPendingApprovalOutcome(outcome)) {
          throw new RunPauseForApproval({
            reply: `${outcome.reason}\n审批编号: ${outcome.pendingApproval.stepId}\n回复「确认」批准，或「拒绝」取消。`,
            iterations: 0,
            toolCalls: 0,
            finalDecision: "WaitForApproval",
            traces: [`post-approval waiting ${outcome.pendingApproval.stepId}`],
          } satisfies ConversationLoopResult)
        }
        return toRunResult(outcome)
      },
    },
  })

  const now = new Date()
  const stepId = crypto.randomUUID()
  await args.wiring.runtimeStore.createStep({
    id: stepId,
    runId: args.runId,
    kind: "result",
    status: "succeeded",
    input: {
      afterCapability: args.capability,
      source: "conversation_loop",
      iterations: loopResult.iterations,
      toolCalls: loopResult.toolCalls,
    },
    createdAt: now,
  })
  await args.wiring.runtimeStore.updateStep({
    stepId,
    output: { reply: loopResult.reply, traces: loopResult.traces },
    updatedAt: now,
  })
  return loopResult.reply
}

/**
 * Resume the same Run after Owner approval: execute the pending capability
 * under the issued ScopedGrant, persist capability Step, then continue with
 * the full multi-turn conversation loop (A7+).
 */
export async function resumeApprovedCapability(
  wiring: Wiring,
  decision: ApprovalDecision,
  options: {
    readonly env?: NodeJS.ProcessEnv
    readonly trigger?: RunTrigger
    readonly content?: string
  } = {},
): Promise<RunResult> {
  const env = options.env ?? process.env
  const pending = parsePendingCapabilityInput(decision.step.input)
  if (!pending) {
    return { ok: false, reason: "invalid pending capability step" }
  }

  const out = await wiring.runEngine.resumeRun(
    {
      runId: decision.runId,
      conversationId: pending.conversationId,
      content: options.content ?? "确认",
      messageId: `approval-resume:${decision.step.id}`,
    },
    async (ctx) => {
      const failRun = async (reason: string): Promise<RunResult> => {
        const current = await wiring.runtimeStore.getRun(ctx.runId)
        if (current?.status === "running") {
          await wiring.runtimeStore.transitionRunStatus(
            current.id,
            current.version,
            "failed",
            new Date(),
          )
        }
        return { ok: false, reason }
      }

      const tools = makeWeibutlerTools({
        bridge: wiring.eventBridge,
        conversationId: pending.conversationId,
        actor: { kind: "agent", id: "approval-resume" },
        ...(pending.wechatUserId ? { wechatUserId: pending.wechatUserId } : {}),
        ...(pending.wechatContextToken ? { wechatContextToken: pending.wechatContextToken } : {}),
        runtimeStore: wiring.runtimeStore,
        runId: ctx.runId,
        env,
        mcpBundle: wiring.mcp,
      })
      const def = findTool(tools, pending.capability)
      if (!def) {
        return failRun(`unknown capability: ${pending.capability}`)
      }
      const executor = makeToolExecutor({
        tools,
        store: wiring.runtimeStore,
        runId: ctx.runId,
        ownerSubject: resolveOwnerSubject(env, pending.subject),
        subject: pending.subject,
        conversationId: pending.conversationId,
        timeoutMsFor: toolTimeoutMs,
        grant: decision.grant,
        mcpServerIdByCapability: wiring.mcp.serverIdByCapability,
      })
      const outcome = await executor.execute(def, pending.args)
      if (isPendingApprovalOutcome(outcome)) {
        return failRun(outcome.reason)
      }
      const result = toRunResult(outcome)
      await persistCapabilityStep(wiring.runtimeStore, {
        runId: ctx.runId,
        capability: pending.capability,
        toolArgs: pending.args,
        approvalStepId: decision.step.id,
        grantId: decision.grant.id,
        result,
      })

      if (options.trigger) {
        await wiring.runtimeStore.appendAuditEvent({
          auditId: crypto.randomUUID(),
          runId: decision.runId,
          conversationId: pending.conversationId,
          action: "approval.resume",
          subject: options.trigger.subject,
          detail: {
            stepId: decision.step.id,
            triggerSource: options.trigger.source,
            trustLevel: options.trigger.trustLevel,
            idempotencyKey: options.trigger.idempotencyKey,
            triggerPayload: options.trigger.payload,
            sameRun: true,
          },
          createdAt: new Date(),
        })
      }

      if (!result.ok) {
        return failRun(result.reason)
      }

      await markGrantConsumed(wiring.runtimeStore, decision.grant)
      const reply = await continueLoopAfterCapability({
        wiring,
        runId: ctx.runId,
        conversationId: pending.conversationId,
        subject: pending.subject,
        capability: pending.capability,
        toolOutput: String(result.output),
        env,
        ...(pending.wechatUserId ? { wechatUserId: pending.wechatUserId } : {}),
        ...(pending.wechatContextToken ? { wechatContextToken: pending.wechatContextToken } : {}),
      })
      await wiring.runtimeStore.appendAuditEvent({
        auditId: crypto.randomUUID(),
        runId: decision.runId,
        conversationId: pending.conversationId,
        action: "approval.executed",
        subject: pending.subject,
        detail: {
          stepId: decision.step.id,
          capability: pending.capability,
          output: reply,
          sameRun: true,
          continuedLoop: true,
        },
        createdAt: new Date(),
      })
      return { ok: true as const, output: reply }
    },
  )

  // runBodyAndFinalize may return a ConversationLoopResult when a nested
  // AskApproval pause escapes the post-approval loop.
  if (isLoopResult(out)) {
    return { ok: true, output: out.reply }
  }
  return out
}
