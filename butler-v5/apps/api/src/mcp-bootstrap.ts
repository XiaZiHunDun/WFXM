import type { LLMTool } from "@butler/adapters"
import type { McpTransport } from "@butler/adapters/mcp/client.js"
import { makeMcpClientAdapter } from "@butler/adapters/mcp/client.js"
import { makeMcpHttpTransport } from "@butler/adapters/mcp/http-transport.js"
import { makeMcpSseTransport } from "@butler/adapters/mcp/sse-transport.js"
import { makeMcpStdioTransport } from "@butler/adapters/mcp/stdio-transport.js"
import type { McpSessionRef } from "@butler/adapters/mcp/session.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { isMcpEnabled } from "@butler/runtime/mcp-gate.js"
import {
  loadMcpLlmTools,
  loadMcpToolDefinitions,
  mcpLlmToolDescriptor,
  type McpDiscoveredTool,
  type McpInvokeFn,
} from "./mcp-tools.js"
import {
  mcpFailClosedOnBootstrap,
  mcpUsesStubTools,
  parseMcpConnectionConfig,
  type McpConnectionConfig,
} from "./mcp-config.js"
import { nodeStdioSpawn } from "./mcp-spawn.js"

export type McpBootstrapMode = "off" | "stub" | McpConnectionConfig["kind"]

export interface McpToolBundle {
  readonly runtimeTools: readonly ToolDefinition[]
  readonly llmTools: readonly LLMTool[]
  readonly mode: McpBootstrapMode
  readonly discovered: readonly McpDiscoveredTool[]
  readonly close?: () => Promise<void>
}

const EMPTY_BUNDLE: McpToolBundle = {
  runtimeTools: [],
  llmTools: [],
  mode: "off",
  discovered: [],
}

function authHeaders(token?: string): Record<string, string> {
  if (!token) return {}
  return { authorization: `Bearer ${token}` }
}

function makeTransport(
  conn: McpConnectionConfig,
  options: {
    readonly fetch?: typeof fetch
    readonly session: McpSessionRef
  },
): McpTransport {
  switch (conn.kind) {
    case "http":
      return makeMcpHttpTransport({
        url: conn.url,
        timeoutMs: conn.timeoutMs,
        headers: authHeaders(conn.token),
        session: options.session,
        ...(options.fetch ? { fetch: options.fetch } : {}),
      })
    case "sse":
      return makeMcpSseTransport({
        url: conn.url,
        timeoutMs: conn.timeoutMs,
        headers: authHeaders(conn.token),
        session: options.session,
        ...(options.fetch ? { fetch: options.fetch } : {}),
      })
    case "stdio":
      return makeMcpStdioTransport({
        command: conn.command,
        args: conn.args,
        timeoutMs: conn.timeoutMs,
        env: conn.env,
        spawn: nodeStdioSpawn,
      })
  }
}

export async function bootstrapMcpTools(
  env: NodeJS.ProcessEnv = process.env,
  options: {
    readonly fetch?: typeof fetch
    readonly discover?: () => Promise<readonly McpDiscoveredTool[]>
    readonly invoke?: McpInvokeFn
    readonly transport?: McpTransport
  } = {},
): Promise<McpToolBundle> {
  if (!isMcpEnabled(env)) {
    return EMPTY_BUNDLE
  }

  if (mcpUsesStubTools(env)) {
    const discovered = mcpStubDiscovered(env)
    const invoke = options.invoke
    return {
      mode: "stub",
      discovered,
      runtimeTools: loadMcpToolDefinitions(env, { discovered, ...(invoke ? { invoke } : {}) }),
      llmTools: loadMcpLlmTools(env, { discovered }),
    }
  }

  const connection = parseMcpConnectionConfig(env)
  if (!connection.ok) {
    if (mcpFailClosedOnBootstrap(env)) {
      throw new Error(`MCP bootstrap failed: ${connection.reason}`)
    }
    return EMPTY_BUNDLE
  }

  try {
    const session: McpSessionRef = {}
    const transport = options.transport ?? makeTransport(connection.value, { ...options, session })
    const client = makeMcpClientAdapter({ transport })
    const discovered = options.discover
      ? await options.discover()
      : (await client.discover()).map((tool) => ({
          name: tool.name,
          description: tool.description,
          inputSchema: tool.inputSchema,
        }))
    const invoke: McpInvokeFn =
      options.invoke ??
      (async (toolName, args) => {
        const result = await client.invoke(toolName, args)
        if (!result.ok) {
          return { ok: false, reason: result.reason ?? "MCP invoke failed" }
        }
        return { ok: true, output: result.output }
      })
    return {
      mode: connection.value.kind,
      discovered,
      runtimeTools: loadMcpToolDefinitions(env, { discovered, invoke }),
      llmTools: discovered.map((tool) => mcpLlmToolDescriptor(tool)),
      close: async () => {
        await transport.close()
      },
    }
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err)
    if (mcpFailClosedOnBootstrap(env)) {
      throw new Error(`MCP bootstrap failed: ${reason}`)
    }
    return EMPTY_BUNDLE
  }
}

function mcpStubDiscovered(env: NodeJS.ProcessEnv): readonly McpDiscoveredTool[] {
  const raw = (env["BUTLER_V5_MCP_TOOL_NAMES"] ?? "").trim()
  if (!raw) return []
  return raw
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .map((name) => ({ name, description: `MCP stub: ${name}` }))
}
