export type RiskLevel = "low" | "medium" | "high"

export type ActionKind = "read" | "write" | "command" | "delegate" | "outbound" | "model"

export interface ActionRequest {
  readonly kind: ActionKind
  readonly capability: string
  readonly subject: string
  readonly resource: string
  readonly risk: RiskLevel
  readonly digest: string
  readonly payload: Readonly<Record<string, unknown>>
}

export type PolicyDecision =
  | { readonly _tag: "Allow" }
  | { readonly _tag: "Deny"; readonly reason: string }
  | {
      readonly _tag: "Ask"
      readonly question: string
      readonly expiresAtMs: number
    }

export interface ScopedGrantScope {
  readonly capabilities: readonly string[]
  readonly paths?: readonly string[]
  readonly network?: "deny" | "allow"
  readonly maxUses?: number
}

export interface ScopedGrantRecord {
  readonly id: string
  readonly runId: string
  readonly subject: string
  readonly scope: ScopedGrantScope
  readonly remainingUses: number | null
  readonly expiresAtMs: number
  readonly createdAtMs: number
}

export interface PermissionPolicy {
  readonly ownerSubject: string
  readonly alwaysConfirm: readonly string[]
  readonly denyByDefault: readonly ActionKind[]
}

export function decidePolicy(
  request: ActionRequest,
  policy: PermissionPolicy,
  nowMs: number,
  grant: ScopedGrantRecord | null,
): PolicyDecision {
  if (policy.alwaysConfirm.includes(request.capability)) {
    return {
      _tag: "Ask",
      question: `Confirm ${request.capability} on ${request.resource}?`,
      expiresAtMs: nowMs + 15 * 60_000,
    }
  }

  if (policy.denyByDefault.includes(request.kind) && request.risk === "high") {
    if (!grant || grant.expiresAtMs <= nowMs) {
      return { _tag: "Deny", reason: "high-risk action without active grant" }
    }
    if (!grant.scope.capabilities.includes(request.capability)) {
      return { _tag: "Deny", reason: "capability not covered by grant" }
    }
    if (grant.remainingUses !== null && grant.remainingUses <= 0) {
      return { _tag: "Deny", reason: "grant exhausted" }
    }
  }

  if (request.risk === "high" && request.subject !== policy.ownerSubject) {
    return { _tag: "Deny", reason: "high-risk action from non-owner subject" }
  }

  return { _tag: "Allow" }
}

export function consumeGrantUse(grant: ScopedGrantRecord): ScopedGrantRecord {
  if (grant.remainingUses === null) return grant
  return { ...grant, remainingUses: Math.max(0, grant.remainingUses - 1) }
}

export function grantMatchesAction(grant: ScopedGrantRecord, request: ActionRequest): boolean {
  return grant.scope.capabilities.includes(request.capability)
}
