import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { ALLOWED_CAPABILITIES } from "@butler/runtime/delegate-runtime.js"
import { revokeScopedGrantsForMcpServer } from "@butler/runtime/mcp-grant-lifecycle.js"
import {
  grantMatchesAction,
  isMcpCapability,
  MCP_CAPABILITY_PREFIX,
} from "@butler/domain/governance/types.js"
import {
  defaultMcpProviderMetadata,
  grantScopeMatchesMcpTool,
  mcpProviderMetadataFromManifest,
  normalizeMcpGrantScope,
  parseMcpCapability,
  scopedGrantScopeTargetsMcpServer,
} from "@butler/domain/governance/mcp-tool-capability.js"
import { parseMcpManifest } from "@butler/domain/mcp/manifest.js"

describe("P3 MCP contract (architecture)", () => {
  it("exports grant lifecycle revoke for provider unload", () => {
    expect(typeof revokeScopedGrantsForMcpServer).toBe("function")
  })

  it("requires per-tool mcp scope for new grants when server id is known", () => {
    const scope = normalizeMcpGrantScope({ serverId: "todoist", toolName: "lst-projects" })
    expect(scope).toEqual({ serverId: "todoist", toolName: "lst-projects" })
    const parsed = parseMcpCapability("mcp_todoist_lst-projects", ["todoist"])
    expect(scope).toBeDefined()
    expect(parsed).toBeDefined()
    if (!scope || !parsed) return
    expect(
      grantScopeMatchesMcpTool(
        {
          capabilities: ["mcp_todoist_lst-projects"],
          digest: "d1",
          mcp: scope,
          network: "allow",
        },
        parsed,
      ),
    ).toBe(true)
  })

  it("denies MCP grant when tool name mismatches scoped grant", () => {
    expect(
      grantMatchesAction(
        {
          id: "g1",
          subject: "owner",
          scope: {
            capabilities: ["mcp_todoist_lst-projects"],
            digest: "d1",
            mcp: { serverId: "todoist", toolName: "lst-projects" },
            network: "allow",
          },
          remainingUses: 1,
          expiresAtMs: Date.now() + 60_000,
          delegable: false,
          approvalId: null,
          sandboxProfile: null,
        },
        {
          capability: "mcp_todoist_get-task",
          kind: "command",
          subject: "owner",
          resource: "mcp_todoist_get-task",
          digest: "d1",
          risk: "low",
        },
      ),
    ).toBe(false)
  })

  it("child subagent allowlist excludes MCP capabilities by default", () => {
    for (const cap of ALLOWED_CAPABILITIES) {
      expect(isMcpCapability(cap)).toBe(false)
    }
    expect(MCP_CAPABILITY_PREFIX).toBe("mcp_")
  })

  it("production manifest declares provider metadata skeleton per server", () => {
    const raw = readFileSync(join(process.cwd(), "config/mcp-manifest.json"), "utf8")
    const parsed = parseMcpManifest(JSON.parse(raw))
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    for (const server of parsed.value.servers) {
      expect(server.defaultRisk).toBe("low")
      expect(server.auditPolicy).toBe("summary")
      expect(server.defaultSandboxProfile).toBe("workspace-write-network-deny")
      expect(
        mcpProviderMetadataFromManifest({
          serverId: server.id,
          defaultRisk: server.defaultRisk,
          auditPolicy: server.auditPolicy,
          defaultSandboxProfile: server.defaultSandboxProfile,
        }),
      ).toEqual({
        serverId: server.id,
        defaultRisk: "low",
        defaultSandboxProfile: "workspace-write-network-deny",
        auditPolicy: "summary",
      })
    }
  })

  it("revoke helper targets grants by normalized server id", () => {
    expect(scopedGrantScopeTargetsMcpServer({ mcp: { serverId: "Todoist", toolName: "x" } }, "todoist")).toBe(
      true,
    )
    expect(defaultMcpProviderMetadata("Demo").serverId).toBe("demo")
  })
})
