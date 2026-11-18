/** MCP Streamable HTTP session id (response header `Mcp-Session-Id`). */
export interface McpSessionRef {
  id?: string
}

export const MCP_PROTOCOL_VERSION = "2024-11-05"

export const MCP_CLIENT_INFO = {
  name: "butler-v5",
  version: "1.0.0",
} as const

export function captureMcpSessionId(
  session: McpSessionRef,
  headers: Headers | Readonly<Record<string, string | undefined>>,
): void {
  const read = (name: string): string | undefined => {
    if (headers instanceof Headers) {
      return headers.get(name) ?? undefined
    }
    const lower = name.toLowerCase()
    for (const [key, value] of Object.entries(headers)) {
      if (key.toLowerCase() === lower && value) return value
    }
    return undefined
  }
  const sessionId = read("mcp-session-id")?.trim()
  if (sessionId) {
    session.id = sessionId
  }
}

export function mcpSessionHeaders(session: McpSessionRef): Record<string, string> {
  const id = session.id?.trim()
  if (!id) return {}
  return { "mcp-session-id": id }
}

export function isMcpNotification(method: string): boolean {
  return method.startsWith("notifications/")
}

export interface McpInitializeParams {
  readonly protocolVersion?: string
  readonly clientInfo?: { readonly name: string; readonly version: string }
}

export function buildMcpInitializeRequest(params: McpInitializeParams = {}): {
  readonly method: "initialize"
  readonly params: {
    readonly protocolVersion: string
    readonly capabilities: Record<string, never>
    readonly clientInfo: { readonly name: string; readonly version: string }
  }
} {
  return {
    method: "initialize",
    params: {
      protocolVersion: params.protocolVersion ?? MCP_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: params.clientInfo ?? MCP_CLIENT_INFO,
    },
  }
}

export function buildMcpInitializedNotification(): {
  readonly method: "notifications/initialized"
  readonly params: Record<string, never>
} {
  return { method: "notifications/initialized", params: {} }
}
