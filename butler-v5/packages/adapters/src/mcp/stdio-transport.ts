import type { McpTransport } from "./client.js"

export interface StdioLineProcess {
  readonly writeLine: (line: string) => void
  readonly onLine: (handler: (line: string) => void) => void
  readonly kill: () => void
}

export type StdioSpawnFn = (
  command: string,
  args: readonly string[],
  options: { readonly env: NodeJS.ProcessEnv },
) => StdioLineProcess

export interface McpStdioTransportConfig {
  readonly command: string
  readonly args: readonly string[]
  readonly env?: Readonly<Record<string, string>>
  readonly timeoutMs?: number
  readonly spawn?: StdioSpawnFn
}

export function makeMcpStdioTransport(config: McpStdioTransportConfig): McpTransport {
  let process: StdioLineProcess | null = null
  let nextId = 0
  const pending = new Map<
    number,
    {
      readonly resolve: (value: { readonly result: unknown }) => void
      readonly reject: (err: Error) => void
      readonly timer: ReturnType<typeof setTimeout>
    }
  >()

  function ensureProcess(): StdioLineProcess {
    if (process) return process
    const spawnFn = config.spawn
    if (!spawnFn) {
      throw new Error("MCP stdio transport unavailable (fail-closed: no spawn handler)")
    }
    const child = spawnFn(config.command, config.args, {
      env: { ...globalThis.process.env, ...config.env },
    })
    child.onLine((line) => {
      const trimmed = line.trim()
      if (!trimmed) return
      let parsed: { readonly id?: number; readonly error?: { readonly message?: string }; readonly result?: unknown }
      try {
        parsed = JSON.parse(trimmed) as typeof parsed
      } catch {
        return
      }
      const id = parsed.id
      if (typeof id !== "number") return
      const waiter = pending.get(id)
      if (!waiter) return
      pending.delete(id)
      clearTimeout(waiter.timer)
      if (parsed.error) {
        waiter.reject(new Error(parsed.error.message ?? "MCP stdio error"))
        return
      }
      waiter.resolve({ result: parsed.result })
    })
    process = child
    return child
  }

  return {
    request: async (req) => {
      const payload = req as { readonly method: string; readonly params?: unknown }
      const id = ++nextId
      const child = ensureProcess()
      const timeoutMs = config.timeoutMs ?? 30_000
      return await new Promise<{ readonly result: unknown }>((resolve, reject) => {
        const timer = setTimeout(() => {
          pending.delete(id)
          reject(new Error(`MCP stdio timeout after ${timeoutMs}ms`))
        }, timeoutMs)
        pending.set(id, { resolve, reject, timer })
        child.writeLine(
          JSON.stringify({
            jsonrpc: "2.0",
            id,
            method: payload.method,
            params: payload.params ?? {},
          }),
        )
      })
    },
    close: async () => {
      for (const waiter of pending.values()) {
        clearTimeout(waiter.timer)
        waiter.reject(new Error("MCP stdio transport closed"))
      }
      pending.clear()
      process?.kill()
      process = null
    },
  }
}
