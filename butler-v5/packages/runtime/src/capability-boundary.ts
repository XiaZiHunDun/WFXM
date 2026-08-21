import type { ActionKind, ScopedGrantRecord } from "@butler/domain/governance/types.js"
import { isMcpCapability } from "@butler/domain/governance/types.js"
import type { PolicyDecision } from "@butler/domain/governance/types.js"
import { createWaitingApprovalStep, type PendingApprovalRequest } from "./approval-runtime.js"
import {
  actionRequestFromTool,
  CapabilityRegistry,
  type CapabilityDefinition,
  type CapabilityProvider,
  type PolicyGate,
} from "./policy-gate.js"
import { runTool, type RunResult, type ToolDefinition } from "./tool-runtime.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"

export type ToolExecutionOutcome =
  | RunResult
  | {
      readonly ok: false
      readonly reason: string
      readonly pendingApproval: { readonly stepId: string; readonly question: string }
    }

export interface ApprovalExecutionContext {
  readonly store: RuntimeStore
  readonly runId: string
  readonly conversationId: string
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
}

export function actionKindForTool(toolName: string): ActionKind {
  switch (toolName) {
    case "run_command":
      return "command"
    case "send_wechat_file":
      return "outbound"
    case "delegate_to_subagent":
      return "delegate"
    case "read_file":
    case "recall_history":
    case "get_current_time":
    case "greet_with_time":
    case "summarize_today":
      return "read"
    default:
      if (isMcpCapability(toolName)) return "command"
      return "read"
  }
}

export function capabilityDefinitionFromTool(def: ToolDefinition): CapabilityDefinition {
  return {
    name: def.name as string,
    kind: actionKindForTool(def.name as string),
    risk: def.risk,
  }
}

export function resourceForTool(
  toolName: string,
  args: Readonly<Record<string, unknown>>,
  fallbackResource: string,
): string {
  if (toolName === "read_file" || toolName === "send_wechat_file") {
    const path = args["path"]
    return typeof path === "string" && path.trim() ? path.trim() : fallbackResource
  }
  if (toolName === "run_command") {
    const argv = args["argv"]
    if (Array.isArray(argv)) {
      return argv.map((part) => String(part)).join(" ")
    }
  }
  if (isMcpCapability(toolName)) {
    return toolName
  }
  return fallbackResource
}

export function buildCapabilityRegistryFromTools(
  tools: readonly ToolDefinition[],
  timeoutMsFor: (toolName: string) => number = () => 5_000,
): CapabilityRegistry {
  const registry = new CapabilityRegistry()
  for (const def of tools) {
    const definition = capabilityDefinitionFromTool(def)
    registry.register(definition, {
      name: definition.name,
      execute: async (request) => runTool(def, { ...request.args }, { timeoutMs: timeoutMsFor(definition.name) }),
    })
  }
  return registry
}

export interface CapabilityProviderRegistration {
  readonly definition: CapabilityDefinition
  readonly provider: CapabilityProvider
}

/** Production registry factory: tools + optional extra providers (MCP, channel, …). */
export function createProductionCapabilityRegistry(args: {
  readonly tools: readonly ToolDefinition[]
  readonly timeoutMsFor?: (toolName: string) => number
  readonly extraProviders?: readonly CapabilityProviderRegistration[]
}): CapabilityRegistry {
  const registry = buildCapabilityRegistryFromTools(
    args.tools,
    args.timeoutMsFor ?? (() => 5_000),
  )
  for (const entry of args.extraProviders ?? []) {
    registry.register(entry.definition, entry.provider)
  }
  return registry
}

export interface ToolBoundaryContext {
  readonly subject: string
  readonly resource: string
  readonly grant: ScopedGrantRecord | null
}

/**
 * Execute a tool through PolicyGate + CapabilityRegistry. All production
 * side effects must use this path instead of calling runTool directly.
 */
export async function executeToolThroughBoundary(
  registry: CapabilityRegistry,
  gate: PolicyGate,
  def: ToolDefinition,
  args: Readonly<Record<string, unknown>>,
  ctx: ToolBoundaryContext,
  approval?: ApprovalExecutionContext,
): Promise<ToolExecutionOutcome> {
  const definition = capabilityDefinitionFromTool(def)
  const request = actionRequestFromTool(
    definition.name,
    ctx.subject,
    ctx.resource,
    args,
    definition,
  )
  const outcome = await registry.executeThroughBoundary(gate, request, args, ctx.grant)
  if (outcome._tag === "Blocked") {
    const decision = outcome.decision
    if (decision._tag === "Ask") {
      if (approval) {
        const step = await persistAskApproval(approval, request, definition, args, decision)
        return {
          ok: false,
          reason: `[待审批] ${decision.question}`,
          pendingApproval: { stepId: step.stepId, question: decision.question },
        }
      }
      return { ok: false, reason: `[需要确认] ${decision.question}` }
    }
    if (decision._tag === "Deny") {
      return { ok: false, reason: `policy denied: ${decision.reason}` }
    }
    return { ok: false, reason: "policy denied" }
  }
  const result = outcome.result
  if (!result.ok) {
    return { ok: false, reason: result.reason ?? "capability failed" }
  }
  return { ok: true, output: result.output }
}

async function persistAskApproval(
  approval: ApprovalExecutionContext,
  request: ReturnType<typeof actionRequestFromTool>,
  definition: CapabilityDefinition,
  args: Readonly<Record<string, unknown>>,
  decision: Extract<PolicyDecision, { readonly _tag: "Ask" }>,
): Promise<{ readonly stepId: string }> {
  const payload: PendingApprovalRequest = {
    runId: approval.runId,
    conversationId: approval.conversationId,
    subject: request.subject,
    capability: definition.name,
    resource: request.resource,
    args,
    question: decision.question,
    expiresAtMs: decision.expiresAtMs,
    digest: request.digest,
    kind: definition.kind,
    risk: definition.risk,
    ...(approval.wechatUserId ? { wechatUserId: approval.wechatUserId } : {}),
    ...(approval.wechatContextToken ? { wechatContextToken: approval.wechatContextToken } : {}),
  }
  return createWaitingApprovalStep(approval.store, payload)
}
