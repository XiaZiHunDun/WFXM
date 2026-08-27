import {
  buildMcpInitializeRequest,
  buildMcpInitializedNotification,
  type McpInitializeParams,
} from "./session.js"

/** JSON-RPC request shape accepted by a transport (params optional for notifications). */
export interface McpRequest {
  readonly method: string
  readonly params?: unknown
}

/** Minimal JSON-RPC response read by the client (`result` only). */
export interface McpResponse {
  readonly result?: unknown
}

/** Transport boundary the McpClient depends on; implemented by http/sse/stdio adapters. */
export interface McpTransport {
  readonly request: (req: McpRequest) => Promise<McpResponse>
  readonly close: () => Promise<void>
}

export interface McpDiscoveredTool {
  readonly name: string
  readonly description: string
  readonly inputSchema: Record<string, unknown>
}

export interface McpInvokeResult {
  readonly ok: boolean
  readonly output?: unknown
  readonly reason?: string
}

export interface McpClientAdapter {
  readonly discover: () => Promise<readonly McpDiscoveredTool[]>
  readonly invoke: (
    toolName: string,
    args: Readonly<Record<string, unknown>>,
  ) => Promise<McpInvokeResult>
  readonly invalidate: (server: string) => Promise<void>
}

export interface McpClientConfig {
  readonly transport: McpTransport
  readonly initialize?: McpInitializeParams
  /** Skip MCP initialize handshake (unit tests only). */
  readonly skipInitialize?: boolean
}

function extractToolOutput(result: unknown): McpInvokeResult {
  if (result === null || typeof result !== "object") {
    return { ok: true, output: result }
  }
  const rec = result as {
    readonly isError?: boolean
    readonly content?: readonly { readonly type?: string; readonly text?: string }[]
  }
  if (rec.isError) {
    const text = rec.content
      ?.filter((part) => part.type === "text" && part.text)
      .map((part) => part.text)
      .join("\n")
    return { ok: false, reason: text?.trim() || "MCP tool returned isError" }
  }
  const text = rec.content
    ?.filter((part) => part.type === "text" && part.text)
    .map((part) => part.text)
    .join("\n")
  if (text !== undefined && text.length > 0) {
    return { ok: true, output: text }
  }
  return { ok: true, output: result }
}

export function makeMcpClientAdapter(config: McpClientConfig): McpClientAdapter {
  let sessionReady = config.skipInitialize === true

  async function ensureSession(): Promise<void> {
    if (sessionReady) return
    await config.transport.request(buildMcpInitializeRequest(config.initialize))
    await config.transport.request(buildMcpInitializedNotification())
    sessionReady = true
  }

  async function resetSession(): Promise<void> {
    sessionReady = config.skipInitialize === true
  }

  return {
    discover: async () => {
      await ensureSession()
      const res = await config.transport.request({ method: "tools/list", params: {} })
      const data = res.result as { tools?: readonly McpDiscoveredTool[] }
      return data.tools ?? []
    },
    invoke: async (toolName, args) => {
      await ensureSession()
      try {
        const res = await config.transport.request({
          method: "tools/call",
          params: { name: toolName, arguments: args },
        })
        return extractToolOutput(res.result)
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        if (/session|initialize|not initialized/i.test(message)) {
          await resetSession()
          await ensureSession()
          const res = await config.transport.request({
            method: "tools/call",
            params: { name: toolName, arguments: args },
          })
          return extractToolOutput(res.result)
        }
        throw err
      }
    },
    invalidate: async (_server: string) => {
      await resetSession()
      await config.transport.close()
    },
  }
}
