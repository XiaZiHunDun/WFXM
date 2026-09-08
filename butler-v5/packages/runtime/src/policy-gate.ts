import type {
  ActionKind,
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
  /** P3-2 declared provider metadata (safety, runtime, idempotency, audit). */
  readonly declared?: CapabilityProviderMetadata
}

/** P3-2: declarative metadata every capability may register (all optional, so
 * existing tools stay on the contract with just name/kind/risk). */
export interface CapabilityProviderMetadata {
  readonly inputSchema?: unknown
  readonly outputSchema?: unknown
  readonly sandboxProfile?: string
  readonly timeoutMs?: number
  readonly idempotent?: boolean
  readonly auditPolicy?: "full" | "summary" | "none"
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

/**
 * Kinds that mutate host/workspace state or cross a trust boundary. The global
 * kill switch hard-stops these regardless of grants; reads (`read`) and model
 * calls (`model`) are observation-only and continue to be allowed.
 */
export const SIDE_EFFECT_KINDS: readonly ActionKind[] = [
  "write",
  "command",
  "outbound",
  "delegate",
]

/** Parse `BUTLER_V5_KILL_SWITCH` (1/true/yes ⇒ on; default off). */
export function readKillSwitch(
  env: Readonly<Record<string, string | undefined>> = {},
): boolean {
  const raw = (env["BUTLER_V5_KILL_SWITCH"] ?? "").trim().toLowerCase()
  return raw === "1" || raw === "true" || raw === "yes"
}

export class PolicyGate {
  constructor(
    private readonly policy: PermissionPolicy,
    private readonly nowMs: () => number,
    private readonly options: { readonly killSwitch?: boolean } = {},
  ) {}

  evaluate(request: ActionRequest, grant: ScopedGrantRecord | null = null): PolicyDecision {
    if (this.options.killSwitch === true && SIDE_EFFECT_KINDS.includes(request.kind)) {
      return { _tag: "Deny", reason: "global kill switch is active (BUTLER_V5_KILL_SWITCH)" }
    }
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

  /** P3-2: declared metadata for a registered capability (undefined if absent).
   * Used to surface schema/sandbox/timeout/idempotency/audit policy. */
  declared(name: string): CapabilityProviderMetadata | undefined {
    return this.definitions.get(name)?.declared
  }

  isRegistered(name: string): boolean {
    return this.definitions.has(name)
  }

  /** P3-2: remove a provider + definition. Grant revocation for the removed
   * capability is handled by the wiring layer (see capability-boundary). */
  unregister(name: string): boolean {
    const existed = this.definitions.delete(name)
    this.providers.delete(name)
    return existed
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

/** Task 2: programs whose argv never mutates sandbox state. */
const READ_ONLY_RUN_COMMANDS = new Set([
  "cat",
  "date",
  "echo",
  "grep",
  "head",
  "ls",
  "pwd",
  "rg",
  "wc",
])

/** Defense-in-depth: shell metachars must never reach a read-only program. */
const SHELL_METACHAR_RE = /[;&|`$<>(){}\\*?\\\n\r]/

/**
 * Classify a `run_command` argv payload's risk. Read-only programs with no
 * shell-metachars → "low" (no approval). Anything else → "high" (approval).
 * Default high: fail-closed when shape is unexpected.
 */
export function classifyRunCommandArgvRisk(argv: unknown): "low" | "high" {
  if (!Array.isArray(argv) || argv.length === 0) return "high"
  const program = argv[0]
  if (typeof program !== "string") return "high"
  if (!READ_ONLY_RUN_COMMANDS.has(program)) return "high"
  for (const a of argv.slice(1)) {
    if (typeof a !== "string") return "high"
    if (SHELL_METACHAR_RE.test(a)) return "high"
  }
  return "low"
}

/** Production loop policy; alwaysConfirm side effects use waiting_approval + Grant. */
export function productionPermissionPolicy(
  ownerSubject: string,
  options: { readonly mcpReadonlyAutoAllow?: boolean } = {},
): PermissionPolicy {
  return {
    ownerSubject,
    alwaysConfirm: ["send_wechat_file", "run_command", "write_file"],
    denyByDefault: ["write", "command", "outbound", "delegate"],
    ...(options.mcpReadonlyAutoAllow ? { mcpReadonlyAutoAllow: true } : {}),
  }
}

export function actionRequestFromTool(
  toolName: string,
  subject: string,
  resource: string,
  args: Readonly<Record<string, unknown>>,
  definition: CapabilityDefinition,
): ActionRequest {
  // Task 2: read-only run_command argv bypasses approval.
  const risk =
    toolName === "run_command"
      ? classifyRunCommandArgvRisk(args["argv"])
      : definition.risk
  return {
    kind: definition.kind,
    capability: toolName,
    subject,
    resource,
    risk,
    digest: `${toolName}:${resource}:${JSON.stringify(args)}`,
    payload: args,
  }
}
