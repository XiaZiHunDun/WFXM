import type { LLMTool } from "@butler/adapters"
import type { McpTransport } from "@butler/adapters/mcp/client.js"
import { makeMcpClientAdapter } from "@butler/adapters/mcp/client.js"
import { makeMcpHttpTransport } from "@butler/adapters/mcp/http-transport.js"
import { makeMcpSseTransport } from "@butler/adapters/mcp/sse-transport.js"
import { makeMcpStdioTransport } from "@butler/adapters/mcp/stdio-transport.js"
import type { McpSessionRef } from "@butler/adapters/mcp/session.js"
import type { McpManifestServer } from "@butler/domain/mcp/manifest.js"
import { mcpServerIds } from "@butler/domain/mcp/manifest.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { isMcpEnabled } from "@butler/runtime/mcp-gate.js"
import { assertMcpServerConsented, mcpServerIdFromEnv } from "@butler/runtime/mcp-consent.js"
import { revokeScopedGrantsForMcpServer } from "@butler/runtime/mcp-grant-lifecycle.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import {
  assertMcpServerInManifest,
  loadMcpManifestFromEnv,
  resolveMcpManifestServer,
} from "./mcp-manifest.js"
import {
  loadMcpLlmTools,
  loadMcpToolDefinitions,
  mcpLlmToolDescriptor,
  type McpDiscoveredTool,
  type McpInvokeFn,
} from "./mcp-tools.js"
import {
  mcpFailClosedOnBootstrap,
  mcpHasServerEndpoint,
  mcpUsesStubTools,
  parseMcpConnectionConfig,
  type McpConnectionConfig,
} from "./mcp-config.js"
import { makeNodeStdioSpawn } from "./mcp-spawn.js"
import type { ExecAuditContext } from "./exec-audit.js"

export type McpBootstrapMode = "off" | "stub" | "multi" | McpConnectionConfig["kind"]

export interface McpServerBootstrap {
  readonly serverId: string
  readonly mode: McpBootstrapMode
  readonly discovered: readonly McpDiscoveredTool[]
}

export interface McpToolBundle {
  readonly runtimeTools: readonly ToolDefinition[]
  readonly llmTools: readonly LLMTool[]
  readonly mode: McpBootstrapMode
  readonly discovered: readonly McpDiscoveredTool[]
  readonly servers: readonly McpServerBootstrap[]
  readonly serverIdByCapability: Readonly<Record<string, string>>
  readonly close?: () => Promise<void>
}

const EMPTY_BUNDLE: McpToolBundle = {
  runtimeTools: [],
  llmTools: [],
  mode: "off",
  discovered: [],
  servers: [],
  serverIdByCapability: {},
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
    readonly audit?: ExecAuditContext
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
        ...(conn.env === undefined ? {} : { env: conn.env }),
        spawn: makeNodeStdioSpawn(options.audit),
      })
  }
}

function resolveServersToBootstrap(
  env: NodeJS.ProcessEnv,
  manifestLoaded: ReturnType<typeof loadMcpManifestFromEnv>,
): readonly string[] {
  const explicit = (env["BUTLER_V5_MCP_SERVER_ID"] ?? "").trim()
  if (explicit) {
    return [explicit]
  }
  if (manifestLoaded.kind === "loaded") {
    return mcpServerIds(manifestLoaded.manifest).filter(
      (serverId) => assertMcpServerConsented(serverId, env).ok,
    )
  }
  return [mcpServerIdFromEnv(env)]
}

function filterDiscoveredByManifest(
  discovered: readonly McpDiscoveredTool[],
  manifestServer: McpManifestServer | null,
): readonly McpDiscoveredTool[] {
  const manifestTools = manifestServer?.tools ?? []
  const allowed = manifestTools.map((tool) => tool.name.trim())
  const riskByName = new Map(
    manifestTools.map((tool) => [tool.name.trim(), tool.risk ?? "high"] as const),
  )
  const filtered =
    allowed.length === 0 ? discovered : discovered.filter((tool) => allowed.includes(tool.name))
  return filtered.map((tool) => {
    const risk = riskByName.get(tool.name)
    return {
      ...tool,
      ...(risk === undefined ? {} : { risk }),
    }
  })
}

function mergeBundles(partials: readonly McpToolBundle[]): McpToolBundle {
  if (partials.length === 0) {
    return EMPTY_BUNDLE
  }
  if (partials.length === 1) {
    const only = partials[0]
    if (!only) {
      return EMPTY_BUNDLE
    }
    return only
  }
  const runtimeTools = partials.flatMap((part) => part.runtimeTools)
  const llmTools = partials.flatMap((part) => part.llmTools)
  const discovered = partials.flatMap((part) => part.discovered)
  const servers = partials.flatMap((part) => part.servers)
  const serverIdByCapability = partials.reduce<Record<string, string>>((acc, part) => {
    return { ...acc, ...part.serverIdByCapability }
  }, {})
  const closeFns = partials
    .map((part) => part.close)
    .filter((fn): fn is () => Promise<void> => !!fn)
  return {
    mode: "multi",
    runtimeTools,
    llmTools,
    discovered,
    servers,
    serverIdByCapability,
    ...(closeFns.length > 0
      ? {
          close: async () => {
            await Promise.all(closeFns.map((fn) => fn()))
          },
        }
      : {}),
  }
}

async function bootstrapSingleMcpServer(
  serverId: string,
  env: NodeJS.ProcessEnv,
  options: {
    readonly fetch?: typeof fetch
    readonly discover?: () => Promise<readonly McpDiscoveredTool[]>
    readonly invoke?: McpInvokeFn
    readonly transport?: McpTransport
    readonly runtimeStore?: RuntimeStore
    readonly manifestLoaded: ReturnType<typeof loadMcpManifestFromEnv>
    readonly namespaced: boolean
  },
): Promise<McpToolBundle> {
  const maybeRevoke = async () => {
    if (options.runtimeStore) {
      await revokeScopedGrantsForMcpServer(options.runtimeStore, serverId)
    }
  }

  const manifestServer =
    options.manifestLoaded.kind === "loaded"
      ? resolveMcpManifestServer(options.manifestLoaded.manifest, serverId)
      : null

  if (options.manifestLoaded.kind === "loaded") {
    const inManifest = assertMcpServerInManifest(options.manifestLoaded.manifest, serverId)
    if (!inManifest.ok) {
      if (mcpFailClosedOnBootstrap(env)) {
        throw new Error(`MCP bootstrap failed: ${inManifest.reason}`)
      }
      await maybeRevoke()
      return EMPTY_BUNDLE
    }
  }

  const consent = assertMcpServerConsented(serverId, env)
  if (!consent.ok) {
    if (mcpFailClosedOnBootstrap(env)) {
      throw new Error(`MCP bootstrap failed: ${consent.reason}`)
    }
    await maybeRevoke()
    return EMPTY_BUNDLE
  }

  if (mcpUsesStubTools(env, manifestServer) && !mcpHasServerEndpoint(env, manifestServer)) {
    const discovered = mcpStubDiscovered(env)
    const invoke = options.invoke
    const toolOptions = {
      serverId,
      ...(options.namespaced ? { namespaced: true as const } : {}),
    }
    const runtimeTools = loadMcpToolDefinitions(env, {
      discovered,
      ...(invoke ? { invoke } : {}),
      ...toolOptions,
    })
    const serverIdByCapability = Object.fromEntries(
      runtimeTools.map((tool) => [tool.name as string, serverId]),
    )
    return {
      mode: "stub",
      discovered,
      runtimeTools,
      llmTools: loadMcpLlmTools(env, { discovered, ...toolOptions }),
      servers: [{ serverId, mode: "stub", discovered }],
      serverIdByCapability,
    }
  }

  const connection = parseMcpConnectionConfig(env, manifestServer, { serverId })
  if (!connection.ok) {
    if (mcpFailClosedOnBootstrap(env)) {
      throw new Error(`MCP bootstrap failed: ${connection.reason}`)
    }
    await maybeRevoke()
    return EMPTY_BUNDLE
  }

  try {
    const session: McpSessionRef = {}
    const audit = options.runtimeStore
      ? { runtimeStore: options.runtimeStore, subject: "mcp" }
      : undefined
    const transport =
      options.transport ??
      makeTransport(connection.value, {
        ...options,
        session,
        ...(audit === undefined ? {} : { audit }),
      })
    const client = makeMcpClientAdapter({ transport })
    const rawDiscovered = options.discover
      ? await options.discover()
      : (await client.discover()).map((tool) => ({
          name: tool.name,
          description: tool.description,
          inputSchema: tool.inputSchema,
        }))
    const discovered = filterDiscoveredByManifest(rawDiscovered, manifestServer)
    const invoke: McpInvokeFn =
      options.invoke ??
      (async (toolName, args) => {
        const result = await client.invoke(toolName, args)
        if (!result.ok) {
          return { ok: false, reason: result.reason ?? "MCP invoke failed" }
        }
        return { ok: true, output: result.output }
      })
    const toolOptions = {
      serverId,
      ...(options.namespaced ? { namespaced: true as const } : {}),
    }
    const runtimeTools = loadMcpToolDefinitions(env, { discovered, invoke, ...toolOptions })
    const serverIdByCapability = Object.fromEntries(
      runtimeTools.map((tool) => [tool.name as string, serverId]),
    )
    return {
      mode: connection.value.kind,
      discovered,
      runtimeTools,
      llmTools: discovered.map((tool) => mcpLlmToolDescriptor(tool, toolOptions)),
      servers: [{ serverId, mode: connection.value.kind, discovered }],
      serverIdByCapability,
      close: async () => {
        await transport.close()
      },
    }
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err)
    if (mcpFailClosedOnBootstrap(env)) {
      throw new Error(`MCP bootstrap failed: ${reason}`)
    }
    await maybeRevoke()
    return EMPTY_BUNDLE
  }
}

export async function bootstrapMcpTools(
  env: NodeJS.ProcessEnv = process.env,
  options: {
    readonly fetch?: typeof fetch
    readonly discover?: () => Promise<readonly McpDiscoveredTool[]>
    readonly invoke?: McpInvokeFn
    readonly transport?: McpTransport
    /** When set, revoke MCP ScopedGrants on disconnect / consent removal (P3). */
    readonly runtimeStore?: RuntimeStore
  } = {},
): Promise<McpToolBundle> {
  if (!isMcpEnabled(env)) {
    const serverId = mcpServerIdFromEnv(env)
    if (options.runtimeStore) {
      await revokeScopedGrantsForMcpServer(options.runtimeStore, serverId)
    }
    return EMPTY_BUNDLE
  }

  const manifestLoaded = loadMcpManifestFromEnv(env)
  if (manifestLoaded.kind === "error") {
    if (mcpFailClosedOnBootstrap(env)) {
      throw new Error(`MCP bootstrap failed: ${manifestLoaded.reason}`)
    }
    return EMPTY_BUNDLE
  }

  const serverIds = resolveServersToBootstrap(env, manifestLoaded)
  const namespaced = serverIds.length > 1
  const partials = (
    await Promise.all(
      serverIds.map(async (serverId) =>
        bootstrapSingleMcpServer(serverId, env, {
          ...options,
          manifestLoaded,
          namespaced,
        }),
      ),
    )
  ).filter((part) => part.runtimeTools.length > 0 || part.mode === "stub")

  if (partials.length === 0) {
    return EMPTY_BUNDLE
  }
  return mergeBundles(partials)
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
