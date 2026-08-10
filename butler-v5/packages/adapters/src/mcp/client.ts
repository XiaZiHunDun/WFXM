interface McpTransport {
  request: (req: unknown) => Promise<{ readonly result: unknown }>
  close: () => Promise<void>
}

interface McpClientConfig {
  readonly transport: McpTransport
}

interface DiscoveredTool {
  readonly name: string
  readonly description: string
  readonly inputSchema: Record<string, unknown>
}

export function makeMcpClientAdapter(config: McpClientConfig) {
  return {
    discover: async () => {
      const res = await config.transport.request({ method: "tools/list" })
      const data = res.result as { tools: readonly DiscoveredTool[] }
      return data.tools
    },
    invalidate: async (_server: string) => {
      await config.transport.close()
    },
  }
}
