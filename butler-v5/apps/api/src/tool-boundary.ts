import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import { resolveSandboxEgressIsolation } from "@butler/domain/governance/network-allowlist.js"
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
import { mcpAllowedForRunSubject } from "@butler/domain/governance/mcp-tool-capability.js"
import {
  PolicyGate,
  productionPermissionPolicy,
  actionRequestFromTool,
  readKillSwitch,
  type CapabilityRegistry,
} from "@butler/runtime/policy-gate.js"
import { markGrantConsumed } from "./approval-resume.js"
import { isMcpReadonlyAutoAllowEnabled } from "./mcp-readonly-policy.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { devSessionRunId } from "./dev-session-grant.js"

export const DEFAULT_TOOL_TIMEOUT_MS = 5_000
export const SEND_WECHAT_FILE_TIMEOUT_MS = 120_000
/** Slirp allowlist (unshare + slirp4netns + iptables) needs well above the default 5s tool budget. */
export const RUN_COMMAND_SLIRP_TIMEOUT_MS = 120_000

function mcpToolTimeoutMs(): number {
  const timeoutMs = Number(process.env["BUTLER_V5_MCP_TIMEOUT_MS"] ?? 30_000)
  return Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 30_000
}

export function runCommandTimeoutMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = env["BUTLER_V5_RUN_COMMAND_TIMEOUT_MS"]?.trim()
  if (raw) {
    const parsed = Number(raw)
    if (Number.isFinite(parsed) && parsed > 0) return parsed
  }
  if (
    (env["BUTLER_V5_SANDBOX"] ?? "").trim() === "bubblewrap" &&
    resolveSandboxEgressIsolation(env) === "slirp"
  ) {
    return RUN_COMMAND_SLIRP_TIMEOUT_MS
  }
  return DEFAULT_TOOL_TIMEOUT_MS
}

export function toolTimeoutMs(toolName: string): number {
  if (toolName === "send_wechat_file") return SEND_WECHAT_FILE_TIMEOUT_MS
  if (toolName.startsWith("mcp_")) return mcpToolTimeoutMs()
  if (toolName === "run_command") return runCommandTimeoutMs()
  return DEFAULT_TOOL_TIMEOUT_MS
}

async function lookupActiveGrant(args: {
  readonly store: RuntimeStore
  readonly runId: string
  readonly subject: string
  readonly capability: string
  readonly resource: string
  readonly digest: string
}): Promise<ScopedGrantRecord | null> {
  const now = new Date()
  const probe = {
    runId: args.runId,
    subject: args.subject,
    capability: args.capability,
    resource: args.resource,
    digest: args.digest,
    now,
  }
  const primary = await args.store.findActiveGrant(probe)
  if (primary) return primary
  const sessionRunId = devSessionRunId(args.subject)
  return args.store.findActiveGrant({
    ...probe,
    runId: sessionRunId,
  })
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
      // P3-3: child/delegated (non-owner) runs get no MCP by default.
      mcpEnabled: mcpAllowedForRunSubject(args.subject, args.ownerSubject),
    }),
  })
  const gate = new PolicyGate(
    productionPermissionPolicy(args.ownerSubject, {
      mcpReadonlyAutoAllow: isMcpReadonlyAutoAllowEnabled(process.env),
    }),
    args.nowMs ?? Date.now,
    { killSwitch: readKillSwitch(process.env) },
  )
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
          ? await lookupActiveGrant({
              store: args.store,
              runId: args.runId,
              subject: args.subject,
              capability: def.name as string,
              resource,
              digest: request.digest,
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
          ...(resolveMcpServerId(def.name as string) === undefined
            ? {}
            : { mcpServerId: resolveMcpServerId(def.name as string) }),
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
