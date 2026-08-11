// infrastructure/mcp — MCP 动态发现 + 工具注册 [OPT-6]
// Phase 3 实现

import { Effect, Layer } from "effect"
import type { DiscoveredTool } from "@butler/domain"
import { MCPDiscovery } from "@butler/ports"

// ─── MCPDiscoveryLive（Phase 3: 骨架，Phase 4: 接入真实 MCP 服务器） ──
export const MCPDiscoveryLive = Layer.effect(
  MCPDiscovery,
  Effect.sync(() => {
    let cache: DiscoveredTool[] | null = null

    return MCPDiscovery.of({
      discover: () =>
        Effect.sync(() => {
          if (cache) return cache
          // Phase 3: 返回内置工具列表（Phase 4: 真实 MCP 发现）
          cache = [
            { name: "read_file", source: "local" as const },
            { name: "write_file", source: "local" as const },
            { name: "execute_command", source: "local" as const },
            { name: "delegate_task", source: "delegate" as const },
          ]
          return cache
        }),

      invalidate: (server) =>
        Effect.sync(() => {
          cache = null
          Effect.logInfo(`[MCP] Cache invalidated for server: ${server}`)
        }),
    })
  }),
)

// ─── 测试用 Mock MCP ────────────────────────────────────
export const MockMCPDiscoveryLive = Layer.succeed(
  MCPDiscovery,
  MCPDiscovery.of({
    discover: () =>
      Effect.succeed([
        { name: "read_file", source: "local" },
        { name: "write_file", source: "local" },
      ]),
    invalidate: () => Effect.void,
  }),
)
