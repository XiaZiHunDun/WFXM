import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import {
  buildCapabilityRegistryFromTools,
  executeToolThroughBoundary,
  resourceForTool,
  type ToolExecutionOutcome,
} from "@butler/runtime/capability-boundary.js"
import {
  PolicyGate,
  productionPermissionPolicy,
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
}): ToolExecutor {
  const registry = buildCapabilityRegistryFromTools(args.tools, args.timeoutMsFor)
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
      const grant =
        explicitGrant ??
        (args.store && args.runId
          ? await args.store.findActiveGrant({
              runId: args.runId,
              subject: args.subject,
              capability: def.name as string,
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
          resource: resourceForTool(def.name as string, toolArgs, args.conversationId),
          grant,
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
