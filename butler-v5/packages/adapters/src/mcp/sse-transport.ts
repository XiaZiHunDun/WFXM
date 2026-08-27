import type { McpTransport } from "./client.js"
import {
  captureMcpSessionId,
  isMcpNotification,
  type McpSessionRef,
} from "./session.js"

export interface McpSseTransportConfig {
  readonly url: string
  readonly fetch?: typeof fetch
  readonly timeoutMs?: number
  readonly headers?: Readonly<Record<string, string>>
  readonly session?: McpSessionRef
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
            accept: "text/event-stream, application/json",
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
            throw new Error(`MCP SSE notification ${res.status}: ${raw.slice(0, 200)}`)
          }
          return { result: null }
        }
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
        return parseSseJsonRpcPayload(raw, id as number)
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          throw new Error(`MCP SSE timeout after ${timeoutMs}ms`)
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
