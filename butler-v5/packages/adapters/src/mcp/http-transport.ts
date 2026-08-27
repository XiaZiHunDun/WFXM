import type { McpTransport } from "./client.js"
import {
  captureMcpSessionId,
  isMcpNotification,
  type McpSessionRef,
} from "./session.js"

export interface McpHttpTransportConfig {
  readonly url: string
  readonly fetch?: typeof fetch
  readonly timeoutMs?: number
  readonly headers?: Readonly<Record<string, string>>
  /** Mutable session ref; `Mcp-Session-Id` is captured from responses. */
  readonly session?: McpSessionRef
}

export function makeMcpHttpTransport(config: McpHttpTransportConfig): McpTransport {
  const fetchFn = config.fetch ?? fetch
  let nextId = 0
  const session: McpSessionRef = config.session ?? {}

  return {
    request: async (req) => {
      const payload = req as { readonly method: string; readonly params?: unknown }
      const isNotification = isMcpNotification(payload.method)
      const id = isNotification ? undefined : ++nextId
      const body = isNotification
        ? JSON.stringify({
            jsonrpc: "2.0",
            method: payload.method,
            params: payload.params ?? {},
          })
        : JSON.stringify({
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
            accept: "application/json",
            ...config.headers,
            ...(session.id ? { "mcp-session-id": session.id } : {}),
          },
          body,
          signal: controller.signal,
        })
        captureMcpSessionId(session, res.headers)
        if (isNotification) {
          if (!res.ok) {
            const raw = await res.text()
            throw new Error(`MCP HTTP notification ${res.status}: ${raw.slice(0, 200)}`)
          }
          return { result: null }
        }
        const raw = await res.text()
        if (!res.ok) {
          throw new Error(`MCP HTTP ${res.status}: ${raw.slice(0, 200)}`)
        }
        let parsed: unknown
        try {
          parsed = JSON.parse(raw) as unknown
        } catch {
          throw new Error("MCP HTTP response is not JSON")
        }
        const json = parsed as {
          readonly error?: { readonly message?: string }
          readonly result?: unknown
        }
        if (json.error) {
          throw new Error(json.error.message ?? "MCP JSON-RPC error")
        }
        return { result: json.result }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          throw new Error(`MCP HTTP timeout after ${timeoutMs}ms`)
        }
        throw err
      } finally {
        clearTimeout(timer)
      }
    },
    close: async () => {
      delete session.id
    },
  }
}
