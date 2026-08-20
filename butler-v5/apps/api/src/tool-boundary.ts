import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import {
  buildCapabilityRegistryFromTools,
  executeToolThroughBoundary,
  resourceForTool,
} from "@butler/runtime/capability-boundary.js"
import {
  PolicyGate,
  productionPermissionPolicy,
  type CapabilityRegistry,
} from "@butler/runtime/policy-gate.js"
import type { RunResult, ToolDefinition } from "@butler/runtime/tool-runtime.js"

export function resolveOwnerSubject(env: NodeJS.ProcessEnv, fallback: string): string {
  const raw = env["BUTLER_OWNER_WECHAT_ID"]?.trim()
  if (!raw) return fallback
  const first = raw
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .find((part) => part.length > 0)
  return first ?? fallback
}

export interface ToolExecutor {
  readonly registry: CapabilityRegistry
  readonly gate: PolicyGate
  readonly execute: (
    def: ToolDefinition,
    args: Readonly<Record<string, unknown>>,
  ) => Promise<RunResult>
}

export function makeToolExecutor(args: {
  readonly tools: readonly ToolDefinition[]
  readonly ownerSubject: string
  readonly subject: string
  readonly conversationId: string
  readonly timeoutMsFor: (toolName: string) => number
  readonly grant?: ScopedGrantRecord | null
  readonly nowMs?: () => number
}): ToolExecutor {
  const registry = buildCapabilityRegistryFromTools(args.tools, args.timeoutMsFor)
  const gate = new PolicyGate(productionPermissionPolicy(args.ownerSubject), args.nowMs ?? Date.now)
  const grant = args.grant ?? null
  return {
    registry,
    gate,
    execute: async (def, toolArgs) =>
      executeToolThroughBoundary(registry, gate, def, toolArgs, {
        subject: args.subject,
        resource: resourceForTool(def.name as string, toolArgs, args.conversationId),
        grant,
      }),
  }
}
