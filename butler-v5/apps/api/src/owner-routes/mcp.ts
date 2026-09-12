import type { Hono } from "hono"
import { revokeScopedGrantsForMcpServer } from "@butler/runtime/mcp-grant-lifecycle.js"
import { mcpServerIdFromEnv } from "@butler/runtime/mcp-consent.js"
import { isMcpEnabled } from "@butler/runtime/mcp-gate.js"
import { defaultMcpProviderMetadata, mcpProviderMetadataFromManifest } from "@butler/domain/governance/mcp-tool-capability.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { loadMcpManifestFromEnv, resolveMcpManifestServer } from "../mcp-manifest.js"

/**
 * Owner control-surface routes for MCP status and scoped-grant revocation.
 * Split from owner-routes.ts (file-size gate) — behavior unchanged.
 */
export function registerMcpRoutes(app: Hono, wiring: Wiring): void {
  app.get("/v1/owner/mcp/status", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const env = process.env
    const enabled = isMcpEnabled(env)
    const bundle = wiring.mcp
    const now = new Date()
    const servers =
      bundle.servers.length > 0
        ? bundle.servers
        : bundle.runtimeTools.length > 0
          ? [
              {
                serverId: mcpServerIdFromEnv(env),
                mode: bundle.mode,
                discovered: bundle.discovered,
              },
            ]
          : []
    const activeGrantsByServer: Record<string, number> = {}
    let activeGrants = 0
    if (enabled) {
      for (const server of servers) {
        const count = await wiring.runtimeStore.countActiveScopedGrantsForMcpServer(
          server.serverId,
          now,
        )
        activeGrantsByServer[server.serverId] = count
        activeGrants += count
      }
    }
    const manifestLoaded = loadMcpManifestFromEnv(env)
    return c.json({
      enabled,
      mode: bundle.mode,
      tools: bundle.runtimeTools.map((t) => t.name),
      discovered: bundle.discovered.map((t) => t.name),
      servers: servers.map((server) => {
        const manifestServer =
          manifestLoaded.kind === "loaded"
            ? resolveMcpManifestServer(manifestLoaded.manifest, server.serverId)
            : null
        const provider = manifestServer
          ? mcpProviderMetadataFromManifest({
              serverId: server.serverId,
              ...(manifestServer.defaultRisk ? { defaultRisk: manifestServer.defaultRisk } : {}),
              ...(manifestServer.defaultSandboxProfile
                ? { defaultSandboxProfile: manifestServer.defaultSandboxProfile }
                : {}),
              ...(manifestServer.auditPolicy ? { auditPolicy: manifestServer.auditPolicy } : {}),
            })
          : defaultMcpProviderMetadata(server.serverId)
        return {
          serverId: server.serverId,
          mode: server.mode,
          tools: bundle.runtimeTools
            .filter((tool) => bundle.serverIdByCapability[tool.name as string] === server.serverId)
            .map((tool) => tool.name),
          discovered: server.discovered.map((tool) => tool.name),
          activeGrants: activeGrantsByServer[server.serverId] ?? 0,
          provider,
        }
      }),
      activeGrants,
    })
  })

  app.post("/v1/owner/mcp/servers/:serverId/revoke-grants", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const serverId = c.req.param("serverId").trim()
    if (!serverId) return c.text("serverId required", 400)
    const body = (await c.req.json().catch(() => ({}))) as { readonly subject?: string }
    const now = new Date()
    // D60 T1.3 (audit #1 F-02): close D59 T1 missed-sweep — the audit_event
    // must record the action even if the underlying revoke throws (same
    // §13 audit completeness gap that D59 T1 closed for 9 other routes).
    let revoked = 0
    let failureReason: string | null = null
    try {
      revoked = await revokeScopedGrantsForMcpServer(wiring.runtimeStore, serverId, now)
    } catch (err) {
      failureReason = err instanceof Error ? err.message : String(err)
    }
    await wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: null,
      action: "mcp.grants_revoked",
      subject: body.subject ?? "owner",
      detail: failureReason
        ? { serverId, revoked, failureReason }
        : { serverId, revoked },
      createdAt: now,
    })
    if (failureReason) {
      return c.json({ ok: false, serverId, error: failureReason }, 500)
    }
    return c.json({ ok: true, serverId, revoked })
  })
}
