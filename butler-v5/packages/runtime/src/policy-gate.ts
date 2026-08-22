import type {
  ActionRequest,
  PermissionPolicy,
  PolicyDecision,
  ScopedGrantRecord,
} from "@butler/domain/governance/types.js"
import { decidePolicy } from "@butler/domain/governance/types.js"
import { runWithSideEffectContext } from "./sandbox/side-effect-context.js"

export interface CapabilityDefinition {
  readonly name: string
  readonly kind: ActionRequest["kind"]
  readonly risk: ActionRequest["risk"]
}

export interface ProviderExecutionRequest {
  readonly capability: string
  readonly args: Readonly<Record<string, unknown>>
  readonly grant: ScopedGrantRecord | null
}

export interface ProviderExecutionResult {
  readonly ok: boolean
  readonly output?: unknown
  readonly reason?: string
}

export interface CapabilityProvider {
  readonly name: string
  readonly execute: (request: ProviderExecutionRequest) => Promise<ProviderExecutionResult>
}

export class PolicyGate {
  constructor(
    private readonly policy: PermissionPolicy,
    private readonly nowMs: () => number,
  ) {}

  evaluate(request: ActionRequest, grant: ScopedGrantRecord | null = null): PolicyDecision {
    return decidePolicy(request, this.policy, this.nowMs(), grant)
  }
}

export class CapabilityRegistry {
  private readonly providers = new Map<string, CapabilityProvider>()
  private readonly definitions = new Map<string, CapabilityDefinition>()

  register(definition: CapabilityDefinition, provider: CapabilityProvider): void {
    this.definitions.set(definition.name, definition)
    this.providers.set(definition.name, provider)
  }

  get(name: string): CapabilityDefinition | undefined {
    return this.definitions.get(name)
  }

  async executeThroughBoundary(
    gate: PolicyGate,
    request: ActionRequest,
    args: Readonly<Record<string, unknown>>,
    grant: ScopedGrantRecord | null,
  ): Promise<
    | { readonly _tag: "Executed"; readonly result: ProviderExecutionResult }
    | { readonly _tag: "Blocked"; readonly decision: PolicyDecision }
  > {
    const decision = gate.evaluate(request, grant)
    if (decision._tag !== "Allow") {
      return { _tag: "Blocked", decision }
    }
    const provider = this.providers.get(request.capability)
    if (!provider) {
      return {
        _tag: "Blocked",
        decision: { _tag: "Deny", reason: `unknown capability ${request.capability}` },
      }
    }
    const result = await runWithSideEffectContext(
      {
        sandboxProfile: grant?.sandboxProfile ?? null,
        networkAllowlist: grant?.networkAllowlist ?? null,
        grantId: grant?.id ?? null,
        capability: request.capability,
      },
      () => provider.execute({ capability: request.capability, args, grant }),
    )
    return { _tag: "Executed", result }
  }
}

export function defaultPermissionPolicy(ownerSubject: string): PermissionPolicy {
  return {
    ownerSubject,
    alwaysConfirm: ["send_wechat_file", "delegate_to_subagent"],
    denyByDefault: ["write", "command", "outbound", "delegate"],
  }
}

/** Production loop policy; alwaysConfirm outbound sends use waiting_approval + Grant. */
export function productionPermissionPolicy(ownerSubject: string): PermissionPolicy {
  return {
    ownerSubject,
    alwaysConfirm: ["send_wechat_file"],
    denyByDefault: ["write", "command", "outbound", "delegate"],
  }
}

export function actionRequestFromTool(
  toolName: string,
  subject: string,
  resource: string,
  args: Readonly<Record<string, unknown>>,
  definition: CapabilityDefinition,
): ActionRequest {
  return {
    kind: definition.kind,
    capability: toolName,
    subject,
    resource,
    risk: definition.risk,
    digest: `${toolName}:${resource}:${JSON.stringify(args)}`,
    payload: args,
  }
}
