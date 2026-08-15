/**
 * Local copy of the minimal tool-runtime surface needed by the
 * wechat butler loop (R8.x.3).
 *
 * The runtime package owns `packages/runtime/src/tool-runtime.ts` with
 * the same shape, but its `exports` map only exposes `bridge.js`.
 * Adding an export entry to the runtime package would be a cross-cutting
 * change outside this task's allowed path scope, so we keep the
 * duplicated surface self-contained here and rely on identical shapes
 * (the runtime tool-runtime is the canonical contract; this file
 * mirrors it for callers that don't have the runtime subpath mapped).
 */

export interface ToolDefinition {
  readonly name: string & { readonly __brand: "ToolName" }
  readonly risk: "low" | "medium" | "high"
  readonly run: (args: Record<string, unknown>, signal?: AbortSignal) => Promise<RunResult>
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
