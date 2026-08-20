import type { McpTransport } from "./client.js"

export interface McpSseTransportConfig {
  readonly url: string
  readonly fetch?: typeof fetch
  readonly timeoutMs?: number
  readonly headers?: Readonly<Record<string, string>>
}

function parseSseJsonRpcPayload(raw: string, expectedId: number): { readonly result: unknown } {
  const chunks = raw.split("\n")
  for (const line of chunks) {
    const trimmed = line.trim()
    if (!trimmed.startsWith("data:")) continue
    const data = trimmed.slice("data:".length).trim()
    if (!data || data === "[DONE]") continue
    let parsed: {
      readonly id?: number
      readonly error?: { readonly message?: string }
      readonly result?: unknown
    }
    try {
      parsed = JSON.parse(data) as typeof parsed
    } catch {
      continue
    }
    if (parsed.id !== expectedId) continue
    if (parsed.error) {
      throw new Error(parsed.error.message ?? "MCP SSE error")
    }
    return { result: parsed.result }
  }
  throw new Error("MCP SSE response missing JSON-RPC data event")
}

export function makeMcpSseTransport(config: McpSseTransportConfig): McpTransport {
  const fetchFn = config.fetch ?? fetch
  let nextId = 0
  return {
    request: async (req) => {
      const payload = req as { readonly method: string; readonly params?: unknown }
      const id = ++nextId
      const body = JSON.stringify({
        jsonrpc: "2.0",
        id,
        method: payload.method,
        params: payload.params ?? {},
      })
      const controller = new AbortController()
      const timeoutMs = config.timeoutMs ?? 30_000
      const timer = setTimeout(() => controller.abort(), timeoutMs)
      try {
        const res = await fetchFn(config.url, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            accept: "text/event-stream, application/json",
            ...config.headers,
          },
          body,
          signal: controller.signal,
        })
        const raw = await res.text()
        if (!res.ok) {
          throw new Error(`MCP SSE HTTP ${res.status}: ${raw.slice(0, 200)}`)
        }
        const contentType = res.headers.get("content-type") ?? ""
        if (contentType.includes("application/json")) {
          const json = JSON.parse(raw) as {
            readonly error?: { readonly message?: string }
            readonly result?: unknown
          }
          if (json.error) {
            throw new Error(json.error.message ?? "MCP SSE JSON-RPC error")
          }
          return { result: json.result }
        }
        return parseSseJsonRpcPayload(raw, id)
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          throw new Error(`MCP SSE timeout after ${timeoutMs}ms`)
        }
        throw err
      } finally {
        clearTimeout(timer)
      }
    },
    close: async () => {},
  }
}
