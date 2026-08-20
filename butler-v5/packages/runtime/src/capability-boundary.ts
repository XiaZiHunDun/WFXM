import type { ActionKind, ScopedGrantRecord } from "@butler/domain/governance/types.js"
import {
  actionRequestFromTool,
  CapabilityRegistry,
  type CapabilityDefinition,
  type PolicyGate,
} from "./policy-gate.js"
import { runTool, type RunResult, type ToolDefinition } from "./tool-runtime.js"

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
): Promise<RunResult> {
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
