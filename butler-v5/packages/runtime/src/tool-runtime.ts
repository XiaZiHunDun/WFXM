import type { CapabilityProviderMetadata } from "./policy-gate.js"

export interface ToolDefinition {
  readonly name: string & { readonly __brand: "ToolName" }
  readonly risk: "low" | "medium" | "high"
  readonly run: (args: Record<string, unknown>, signal?: AbortSignal) => Promise<RunResult>
  /** P3-2: provider-declared metadata (all optional; defaults are applied by kind in
   * `capabilityDefinitionFromTool` — schema is only present when a real source exists). */
  readonly declared?: CapabilityProviderMetadata
}

export type RunResult =
  { readonly ok: true; readonly output: unknown } | { readonly ok: false; readonly reason: string }

export interface RunOptions {
  readonly timeoutMs: number
  readonly signal?: AbortSignal
}

export type RunOutcome = RunResult

export async function runTool(
  def: ToolDefinition,
  args: Record<string, unknown>,
  opts: RunOptions,
): Promise<RunOutcome> {
  let timer: ReturnType<typeof setTimeout> | null = null
  let timedOut = false

  // internal abort for both timeout and caller's signal
  const internal = new AbortController()
  const onCallerAbort = () => internal.abort()
  if (opts.signal) {
    if (opts.signal.aborted) {
      return {
        ok: false,
        reason: opts.signal.reason instanceof Error ? opts.signal.reason.message : "aborted",
      }
    }
    opts.signal.addEventListener("abort", onCallerAbort)
  }

  const timeoutPromise = new Promise<RunOutcome>((resolve) => {
    timer = setTimeout(() => {
      timedOut = true
      internal.abort()
      resolve({ ok: false, reason: `timeout after ${opts.timeoutMs}ms` })
    }, opts.timeoutMs)
  })

  let handlerPromise: Promise<RunResult>
  try {
    handlerPromise = def.run(args, internal.signal)
  } catch (err) {
    // Synchronous throw — should be rare; run is expected to be async
    if (timer) clearTimeout(timer)
    if (opts.signal) opts.signal.removeEventListener("abort", onCallerAbort)
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }

  try {
    const result = await Promise.race([handlerPromise, timeoutPromise])
    if (timer) clearTimeout(timer)
    if (opts.signal) opts.signal.removeEventListener("abort", onCallerAbort)
    return result
  } catch (err) {
    if (timer) clearTimeout(timer)
    if (opts.signal) opts.signal.removeEventListener("abort", onCallerAbort)
    if (timedOut) {
      return { ok: false, reason: `timeout after ${opts.timeoutMs}ms` }
    }
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, reason: "aborted" }
    }
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }
}
