import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import {
  capabilityDefinitionFromTool,
  createProductionCapabilityRegistry,
  executeToolThroughBoundary,
  mcpCapabilityProvidersFromTools,
  resourceForTool,
  splitCoreAndMcpTools,
  type ToolExecutionOutcome,
} from "@butler/runtime/capability-boundary.js"
import { mcpServerIdForCapability } from "@butler/runtime/mcp-consent.js"
import {
  PolicyGate,
  productionPermissionPolicy,
  actionRequestFromTool,
  type CapabilityRegistry,
} from "@butler/runtime/policy-gate.js"
import { markGrantConsumed } from "./approval-resume.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"

export const DEFAULT_TOOL_TIMEOUT_MS = 5_000
export const SEND_WECHAT_FILE_TIMEOUT_MS = 120_000

export function toolTimeoutMs(toolName: string): number {
  return toolName === "send_wechat_file" ? SEND_WECHAT_FILE_TIMEOUT_MS : DEFAULT_TOOL_TIMEOUT_MS
}

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
  ) => Promise<ToolExecutionOutcome>
}

export function makeToolExecutor(args: {
  readonly tools: readonly ToolDefinition[]
  readonly ownerSubject: string
  readonly subject: string
  readonly conversationId: string
  readonly timeoutMsFor: (toolName: string) => number
  readonly grant?: ScopedGrantRecord | null
  readonly nowMs?: () => number
  readonly store?: RuntimeStore
  readonly runId?: string
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
  readonly mcpServerIdByCapability?: Readonly<Record<string, string>>
}): ToolExecutor {
  const { core, mcp } = splitCoreAndMcpTools(args.tools)
  const resolveMcpServerId = (capability: string): string | undefined =>
    args.mcpServerIdByCapability?.[capability] ?? mcpServerIdForCapability(capability, process.env)
  const registry = createProductionCapabilityRegistry({
    tools: core,
    timeoutMsFor: args.timeoutMsFor,
    extraProviders: mcpCapabilityProvidersFromTools(mcp, {
      timeoutMsFor: args.timeoutMsFor,
    }),
  })
  const gate = new PolicyGate(productionPermissionPolicy(args.ownerSubject), args.nowMs ?? Date.now)
  const approval =
    args.store && args.runId
      ? {
          store: args.store,
          runId: args.runId,
          conversationId: args.conversationId,
          ...(args.wechatUserId ? { wechatUserId: args.wechatUserId } : {}),
          ...(args.wechatContextToken ? { wechatContextToken: args.wechatContextToken } : {}),
        }
      : undefined
  return {
    registry,
    gate,
    execute: async (def, toolArgs) => {
      const explicitGrant = args.grant ?? null
      const definition = capabilityDefinitionFromTool(def)
      const resource = resourceForTool(def.name as string, toolArgs, args.conversationId)
      const request = actionRequestFromTool(
        definition.name,
        args.subject,
        resource,
        toolArgs,
        definition,
      )
      const grant =
        explicitGrant ??
        (args.store && args.runId
          ? await args.store.findActiveGrant({
              runId: args.runId,
              subject: args.subject,
              capability: def.name as string,
              resource,
              digest: request.digest,
              now: new Date(),
            })
          : null)
      const outcome = await executeToolThroughBoundary(
        registry,
        gate,
        def,
        toolArgs,
        {
          subject: args.subject,
          resource,
          grant,
          ...(resolveMcpServerId(def.name as string)
            ? { mcpServerId: resolveMcpServerId(def.name as string) }
            : {}),
        },
        approval,
      )
      if (!explicitGrant && grant && outcome.ok && args.store) {
        await markGrantConsumed(args.store, grant)
      }
      return outcome
    },
  }
}
