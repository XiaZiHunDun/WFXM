export interface McpTransport {
  readonly request: (req: unknown) => Promise<{ readonly result: unknown }>
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
  return {
    discover: async () => {
      const res = await config.transport.request({ method: "tools/list", params: {} })
      const data = res.result as { tools?: readonly McpDiscoveredTool[] }
      return data.tools ?? []
    },
    invoke: async (toolName, args) => {
      const res = await config.transport.request({
        method: "tools/call",
        params: { name: toolName, arguments: args },
      })
      return extractToolOutput(res.result)
    },
    invalidate: async (_server: string) => {
      await config.transport.close()
    },
  }
}
