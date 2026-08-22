/**
 * Side-effect execution context (A8).
 *
 * CapabilityRegistry sets this around Provider.execute so tools
 * (run_command / MCP) can read Grant.sandboxProfile without threading
 * it through ToolDefinition.run args.
 */
import { AsyncLocalStorage } from "node:async_hooks"

export interface SideEffectExecutionContext {
  readonly sandboxProfile: string | null
  readonly networkAllowlist: readonly string[] | null
  readonly grantId: string | null
  readonly capability: string
}

const storage = new AsyncLocalStorage<SideEffectExecutionContext>()

export function runWithSideEffectContext<T>(
  ctx: SideEffectExecutionContext,
  fn: () => Promise<T>,
): Promise<T> {
  return storage.run(ctx, fn)
}

export function currentSideEffectContext(): SideEffectExecutionContext | undefined {
  return storage.getStore()
}

export function currentSandboxProfileName(): string | null {
  return storage.getStore()?.sandboxProfile ?? null
}

export function currentNetworkAllowlist(): readonly string[] | null {
  return storage.getStore()?.networkAllowlist ?? null
}
