/**
 * Pre-issue ScopedGrants for delegated subagent tool runs.
 *
 * When the owner delegates with `run_command` or `write_file`, the delegate
 * intent is treated as approval; the child run receives multi-use grants so
 * the worker can execute without a live WeChat confirmation loop.
 *
 * Under P2 allowlist (`BUTLER_V5_SANDBOX_NETWORK_MODE=allowlist`), `run_command`
 * is NOT pre-granted: each shell invocation goes through waiting_approval so
 * Owner can stamp `networkAllowlist` on approve (Scheme B network E2E).
 */
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { resolveSandboxNetworkMode } from "@butler/domain/governance/network-allowlist.js"
import { issuePreconfiguredGrants } from "@butler/runtime/scoped-grant-service.js"
import { executableCapabilities } from "./capability-guard.js"

const DELEGATION_CONFIRM_TOOLS = ["run_command", "write_file"] as const

const DELEGATION_GRANT_TTL_MS = 60 * 60 * 1000

export function delegationPregrantCapabilities(args: {
  readonly capabilities: readonly string[]
  readonly env?: NodeJS.ProcessEnv
}): readonly string[] {
  const env = args.env ?? process.env
  const granted = executableCapabilities(args.capabilities).filter((cap) =>
    (DELEGATION_CONFIRM_TOOLS as readonly string[]).includes(cap),
  )
  if (resolveSandboxNetworkMode(env) !== "allowlist") {
    return granted
  }
  return granted.filter((cap) => cap !== "run_command")
}

export async function ensureDelegationToolGrants(args: {
  readonly store: RuntimeStore
  readonly childRunId: string
  readonly ownerSubject: string
  readonly capabilities: readonly string[]
  readonly maxUses: number
  readonly env?: NodeJS.ProcessEnv
}): Promise<void> {
  const granted = delegationPregrantCapabilities({
    capabilities: args.capabilities,
    ...(args.env ? { env: args.env } : {}),
  })
  if (granted.length === 0) return
  await issuePreconfiguredGrants({
    store: args.store,
    runId: args.childRunId,
    subject: args.ownerSubject,
    capabilities: granted,
    maxUses: args.maxUses,
    ttlMs: DELEGATION_GRANT_TTL_MS,
  })
}
