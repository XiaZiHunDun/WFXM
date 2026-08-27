import type { ActionKind, RiskLevel, ScopedGrantRecord } from "@butler/domain/governance/types.js"
import { buildScopedGrantScopeFromPending } from "@butler/domain/governance/types.js"
import { isMcpCapability } from "@butler/domain/governance/types.js"
import {
  hashNetworkAllowlistForAudit,
  hostnamesFromNetworkAllowlist,
  SANDBOX_PROFILE_NETWORK_ALLOWLIST,
  validateNetworkAllowlist,
  envAllowPrivateEgress,
} from "@butler/domain/governance/network-allowlist.js"
import { outboundNetworkHostsForCapability } from "./grant-network.js"
import { mcpServerIdForCapability } from "./mcp-consent.js"
import type { RuntimeStore, StoredStep } from "@butler/domain/runtime.js"
import {
  parseSandboxProfileName,
  sandboxProfileForApprovedCapability,
} from "./sandbox/profiles.js"

export interface PendingCapabilityInput {
  readonly _tag: "PendingCapability"
  readonly capability: string
  readonly args: Readonly<Record<string, unknown>>
  readonly conversationId: string
  readonly subject: string
  readonly resource: string
  readonly question: string
  readonly expiresAtMs: number
  readonly digest: string
  readonly kind: ActionKind
  readonly risk: RiskLevel
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
}

export interface PendingApprovalRequest {
  readonly runId: string
  readonly conversationId: string
  readonly subject: string
  readonly capability: string
  readonly resource: string
  readonly args: Readonly<Record<string, unknown>>
  readonly question: string
  readonly expiresAtMs: number
  readonly digest: string
  readonly kind: ActionKind
  readonly risk: RiskLevel
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
}

export function parsePendingCapabilityInput(
  input: Readonly<Record<string, unknown>>,
): PendingCapabilityInput | null {
  if (input["_tag"] !== "PendingCapability") return null
  const capability = input["capability"]
  const conversationId = input["conversationId"]
  const subject = input["subject"]
  const question = input["question"]
  if (
    typeof capability !== "string" ||
    typeof conversationId !== "string" ||
    typeof subject !== "string" ||
    typeof question !== "string"
  ) {
    return null
  }
  return input as unknown as PendingCapabilityInput
}

export async function createWaitingApprovalStep(
  store: RuntimeStore,
  request: PendingApprovalRequest,
): Promise<{ readonly stepId: string }> {
  const run = await store.getRun(request.runId)
  if (!run) {
    throw new Error(`run not found: ${request.runId}`)
  }
  await store.transitionRunStatus(run.id, run.version, "waiting_approval", new Date())
  const stepId = crypto.randomUUID()
  const now = new Date()
  const pending: PendingCapabilityInput = {
    _tag: "PendingCapability",
    capability: request.capability,
    args: request.args,
    conversationId: request.conversationId,
    subject: request.subject,
    resource: request.resource,
    question: request.question,
    expiresAtMs: request.expiresAtMs,
    digest: request.digest,
    kind: request.kind,
    risk: request.risk,
    ...(request.wechatUserId ? { wechatUserId: request.wechatUserId } : {}),
    ...(request.wechatContextToken ? { wechatContextToken: request.wechatContextToken } : {}),
  }
  await store.createStep({
    id: stepId,
    runId: request.runId,
    kind: "approval",
    status: "waiting",
    input: pending as unknown as Readonly<Record<string, unknown>>,
    createdAt: now,
  })
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: request.runId,
    conversationId: request.conversationId,
    action: "approval.requested",
    subject: request.subject,
    detail: {
      stepId,
      capability: request.capability,
      digest: request.digest,
      question: request.question,
    },
    createdAt: now,
  })
  return { stepId }
}

export interface ApprovalDecision {
  readonly step: StoredStep
  readonly grant: ScopedGrantRecord
  readonly runId: string
}

/**
 * Idempotent outcome for `approveWaitingStep`.
 * - `approved`: a ScopedGrant was freshly issued and the Run resumed (terminal action).
 * - `alreadyProcessed`: the approval Step was not in `waiting` (or had expired), so NO
 *   new Grant is issued and no Run is resumed. Repeated replies / timeouts therefore
 *   acknowledge idempotently instead of double-granting (P1 acceptance).
 */
export type ApproveOutcome =
  | (ApprovalDecision & { readonly _tag: "approved" })
  | {
      readonly _tag: "alreadyProcessed"
      readonly step: StoredStep
      readonly runId: string
      readonly reason: string
    }

export async function approveWaitingStep(
  store: RuntimeStore,
  stepId: string,
  ownerSubject: string,
  options: {
    /** Elevate sandbox to network-allow (must be stamped on Grant). */
    readonly elevateNetwork?: boolean
    /** Explicit profile name; overrides elevateNetwork when valid. */
    readonly sandboxProfile?: string | null
    /** host:port egress allowlist → workspace-write-network-allowlist (P2b). */
    readonly networkAllowlist?: readonly string[]
    readonly env?: NodeJS.ProcessEnv
  } = {},
): Promise<ApproveOutcome> {
  const step = await store.getStep(stepId)
  if (!step || step.kind !== "approval") {
    throw new Error(`approval step not found: ${stepId}`)
  }
  if (step.status !== "waiting") {
    return {
      _tag: "alreadyProcessed",
      step,
      runId: step.runId,
      reason: `step already terminal (${step.status})`,
    }
  }
  const pending = parsePendingCapabilityInput(step.input)
  if (!pending) {
    throw new Error(`invalid pending capability on step ${stepId}`)
  }
  if (Date.now() > pending.expiresAtMs) {
    await denyWaitingStep(store, stepId, ownerSubject, "expired")
    return { _tag: "alreadyProcessed", step, runId: step.runId, reason: "expired" }
  }
  const run = await store.getRun(step.runId)
  if (!run) {
    throw new Error(`run not found for step ${stepId}`)
  }
  const env = options.env ?? process.env
  if (options.elevateNetwork === true && options.networkAllowlist && options.networkAllowlist.length > 0) {
    throw new Error("elevateNetwork and networkAllowlist are mutually exclusive")
  }
  let normalizedAllowlist: readonly string[] | null = null
  if (options.networkAllowlist && options.networkAllowlist.length > 0) {
    const validated = validateNetworkAllowlist(options.networkAllowlist, {
      allowPrivateEgress: envAllowPrivateEgress(env),
    })
    if (!validated.ok) {
      throw new Error(validated.reason)
    }
    normalizedAllowlist = validated.normalized
  }
  const explicitProfile = parseSandboxProfileName(options.sandboxProfile)
  if (explicitProfile === SANDBOX_PROFILE_NETWORK_ALLOWLIST && !normalizedAllowlist) {
    throw new Error("sandboxProfile network-allowlist requires networkAllowlist")
  }
  const sandboxProfile =
    explicitProfile ??
    (normalizedAllowlist
      ? SANDBOX_PROFILE_NETWORK_ALLOWLIST
      : sandboxProfileForApprovedCapability(pending.capability, {
          elevateNetwork: options.elevateNetwork === true,
        }))
  const outboundHosts = outboundNetworkHostsForCapability(pending.capability, env)
  const allowlistHosts = normalizedAllowlist
    ? hostnamesFromNetworkAllowlist(normalizedAllowlist)
    : undefined
  const networkHosts =
    allowlistHosts && allowlistHosts.length > 0
      ? [...new Set([...(outboundHosts ?? []), ...allowlistHosts])]
      : outboundHosts
  const now = new Date()
  const mcpServerId = isMcpCapability(pending.capability)
    ? mcpServerIdForCapability(pending.capability, env)
    : undefined
  const grant = await store.createScopedGrant({
    grantId: crypto.randomUUID(),
    runId: step.runId,
    subject: pending.subject,
    scope: buildScopedGrantScopeFromPending({
      capability: pending.capability,
      resource: pending.resource,
      digest: pending.digest,
      ...(networkHosts !== undefined ? { networkHosts } : {}),
      forceNetworkAllow: normalizedAllowlist !== null,
      ...(mcpServerId !== undefined ? { mcpServerId } : {}),
    }),
    remainingUses: 1,
    expiresAt: new Date(pending.expiresAtMs),
    createdAt: now,
    delegable: false,
    approvalId: stepId,
    sandboxProfile,
    networkAllowlist: normalizedAllowlist,
  })
  await store.updateStep({
    stepId,
    status: "succeeded",
    output: { approvedBy: ownerSubject, grantId: grant.id },
    updatedAt: now,
  })
  await store.transitionRunStatus(run.id, run.version, "running", now)
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: step.runId,
    conversationId: pending.conversationId,
    action: "approval.granted",
    subject: ownerSubject,
    detail: {
      stepId,
      capability: pending.capability,
      grantId: grant.id,
      ...(grant.sandboxProfile ? { sandboxProfile: grant.sandboxProfile } : {}),
      ...(grant.networkAllowlist && grant.networkAllowlist.length > 0
        ? { networkAllowlistHash: hashNetworkAllowlistForAudit(grant.networkAllowlist) }
        : {}),
      ...(grant.scope.mcp
        ? { mcpServerId: grant.scope.mcp.serverId, mcpToolName: grant.scope.mcp.toolName }
        : {}),
    },
    createdAt: now,
  })
  return { _tag: "approved", step, grant, runId: step.runId }
}

/**
 * Idempotent outcome for `denyWaitingStep`.
 * - `false`: the Step was freshly denied (waiting → failed).
 * - `true`: the Step was already terminal; nothing was re-written or re-audited.
 */
export type DenyOutcome = { readonly alreadyProcessed: boolean }

export async function denyWaitingStep(
  store: RuntimeStore,
  stepId: string,
  ownerSubject: string,
  reason = "denied",
): Promise<DenyOutcome> {
  const step = await store.getStep(stepId)
  if (!step) {
    throw new Error(`step not found: ${stepId}`)
  }
  if (step.kind !== "approval") {
    throw new Error(`step is not an approval step: ${stepId}`)
  }
  if (step.status !== "waiting") {
    return { alreadyProcessed: true }
  }
  const pending = parsePendingCapabilityInput(step.input)
  const now = new Date()
  await store.updateStep({
    stepId,
    status: "failed",
    output: { deniedBy: ownerSubject, reason },
    updatedAt: now,
  })
  const run = await store.getRun(step.runId)
  if (run && run.status === "waiting_approval") {
    await store.transitionRunStatus(run.id, run.version, "failed", now)
  }
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: step.runId,
    conversationId: pending?.conversationId ?? null,
    action: "approval.denied",
    subject: ownerSubject,
    detail: { stepId, reason },
    createdAt: now,
  })
  return { alreadyProcessed: false }
}
