import type { ActionKind, ScopedGrantRecord } from "@butler/domain/governance/types.js"
import { isMcpCapability } from "@butler/domain/governance/types.js"
import { defaultMcpProviderMetadata } from "@butler/domain/governance/mcp-tool-capability.js"
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
import { getSharedLocalTracer } from "./observability/local-tracer.js"

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
    case "write_file":
      return "write"
    case "read_file":
    case "recall_history":
    case "recall_durable_memory":
    case "recall_document":
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
  if (toolName === "read_file" || toolName === "write_file" || toolName === "send_wechat_file") {
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

export function splitCoreAndMcpTools(tools: readonly ToolDefinition[]): {
  readonly core: readonly ToolDefinition[]
  readonly mcp: readonly ToolDefinition[]
} {
  const core: ToolDefinition[] = []
  const mcp: ToolDefinition[] = []
  for (const def of tools) {
    if (isMcpCapability(def.name as string)) {
      mcp.push(def)
    } else {
      core.push(def)
    }
  }
  return { core, mcp }
}

/**
 * P3-2: uninstall a capability provider and make related Grants expire
 * (fail-consistent): removes the provider/definition from the registry now, then
 * revokes every active Grant whose scope targets that capability via the store.
 * Returns how many Grants were revoked so the caller can surface it in audit.
 */
export async function unregisterCapability(args: {
  readonly registry: CapabilityRegistry
  readonly name: string
  readonly store?: RuntimeStore | null
  readonly now?: Date
}): Promise<{ readonly removed: boolean; readonly revokedGrants: number }> {
  const removed = args.registry.unregister(args.name)
  let revokedGrants = 0
  if (removed && args.store) {
    revokedGrants = await args.store.revokeScopedGrantsForCapability(
      args.name,
      args.now ?? new Date(),
    )
  }
  return { removed, revokedGrants }
}

/** Register MCP ToolDefinitions as explicit extra providers on the production registry.
 * MCP execute runs under the same side-effect sandbox context as core tools (A8).
 */
export function mcpCapabilityProvidersFromTools(
  tools: readonly ToolDefinition[],
  options: {
    readonly timeoutMsFor?: (toolName: string) => number
    readonly serverId?: string
    /** P3-3: default true; pass false to give a (child/delegated) run no MCP. */
    readonly mcpEnabled?: boolean
  } = {},
): readonly CapabilityProviderRegistration[] {
  if (options.mcpEnabled === false) return []
  const timeoutMsFor = options.timeoutMsFor ?? (() => 5_000)
  return tools.map((def) => {
    const definition = capabilityDefinitionFromTool(def)
    return {
      definition,
      provider: {
        name: definition.name,
        execute: async (request) =>
          runTool(def, { ...request.args }, { timeoutMs: timeoutMsFor(definition.name) }),
      },
    }
  })
}

export interface ToolBoundaryContext {
  readonly subject: string
  readonly resource: string
  readonly grant: ScopedGrantRecord | null
  readonly mcpServerId?: string
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
  const tracer = getSharedLocalTracer()
  const policyTag = outcome._tag === "Blocked" ? outcome.decision._tag : "Allow"
  tracer.record({
    kind: "policy",
    name: policyTag,
    status: outcome._tag === "Blocked" && outcome.decision._tag === "Deny" ? "error" : "ok",
    runId: approval?.runId ?? null,
    conversationId: approval?.conversationId ?? null,
    subject: ctx.subject,
    capability: definition.name,
    policyDecision: policyTag,
    grantId: ctx.grant?.id ?? null,
    detail: { resource: ctx.resource },
  })
  if (outcome._tag === "Blocked") {
    const decision = outcome.decision
    if (decision._tag === "Ask") {
      if (approval) {
        const step = await persistAskApproval(approval, request, definition, args, decision)
        tracer.record({
          kind: "approval",
          name: "requested",
          status: "waiting",
          runId: approval.runId,
          conversationId: approval.conversationId,
          stepId: step.stepId,
          waitingStepId: step.stepId,
          subject: ctx.subject,
          capability: definition.name,
          policyDecision: "Ask",
        })
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
  const started = Date.now()
  const result = outcome.result
  const mcpProvider =
    isMcpCapability(definition.name) && ctx.mcpServerId
      ? defaultMcpProviderMetadata(ctx.mcpServerId)
      : null
  tracer.record({
    kind: "capability",
    name: definition.name,
    status: result.ok ? "ok" : "error",
    runId: approval?.runId ?? null,
    conversationId: approval?.conversationId ?? null,
    subject: ctx.subject,
    capability: definition.name,
    grantId: ctx.grant?.id ?? null,
    durationMs: Date.now() - started,
    detail: {
      resource: ctx.resource,
      ...(result.ok ? { ok: true } : { reason: result.reason ?? "failed" }),
      ...(mcpProvider
        ? {
            mcpServerId: mcpProvider.serverId,
            auditPolicy: mcpProvider.auditPolicy,
            sandboxProfile: mcpProvider.defaultSandboxProfile,
            risk: definition.risk,
          }
        : {}),
      ...(ctx.grant?.scope.mcp
        ? {
            grantMcpServerId: ctx.grant.scope.mcp.serverId,
            grantMcpToolName: ctx.grant.scope.mcp.toolName,
          }
        : {}),
    },
  })
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
