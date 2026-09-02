import { describe, expect, it } from "vitest"
import {
  defaultMcpProviderMetadata,
  grantScopeMatchesMcpTool,
  mcpAllowedForRunSubject,
  mcpProviderMetadataFromManifest,
  mcpToolsFromServer,
  normalizeMcpGrantScope,
  parseMcpCapability,
  rejectMcpTokenPassthrough,
  resolveMcpOAuthAudience,
  resolveMcpToolRisk,
  scopedGrantScopeTargetsMcpServer,
  toMcpCapabilityName,
  toMcpCapabilityNameForServer,
} from "./mcp-tool-capability.js"
import { isMcpCapability, MCP_CAPABILITY_PREFIX, normalizeMcpServerId, normalizeMcpToolName, resolveMcpServerIdFromCapability } from "./mcp-tool-capability.js"

describe("P3-3 named registry / untrusted descriptions", () => {
  it("treats tool descriptions as untrusted: server default risk is authoritative", () => {
    expect(
      resolveMcpToolRisk({ id: "s", defaultRisk: "high", tools: [] }, { risk: "low" }),
    ).toBe("high")
    expect(resolveMcpToolRisk({ id: "s", defaultRisk: "low", tools: [] }, { risk: "high" })).toBe("low")
  })

  it("scales a refused risk up to the fail-closed default when server omits it", () => {
    expect(resolveMcpToolRisk({ id: "s", tools: [] }, { risk: "low" })).toBe("high")
  })

  it("maps a named server + tools into concrete per-tool capabilities", () => {
    const tools = mcpToolsFromServer({
      id: "github",
      defaultRisk: "high",
      tools: [{ name: "search", risk: "low" }, { name: "read" }],
    })
    expect(tools).toEqual([
      { toolName: "search", capability: "mcp_github_search", risk: "high", serverId: "github" },
      { toolName: "read", capability: "mcp_github_read", risk: "high", serverId: "github" },
    ])
  })

  it("defaults Child (non-owner) runs to no MCP", () => {
    expect(mcpAllowedForRunSubject("owner-1", "owner-1")).toBe(true)
    expect(mcpAllowedForRunSubject("delegate-sub", "owner-1")).toBe(false)
  })
})

describe("P3-3 remote OAuth audience binding / no token passthrough", () => {
  it("derives audience only for remote servers with an explicit oauthAudience", () => {
    expect(resolveMcpOAuthAudience({ id: "x", transport: "http", url: "https://api.example.com", oauthAudience: "api.example.com", tools: [] })).toBe("api.example.com")
    expect(resolveMcpOAuthAudience({ id: "x", transport: "http", url: "https://api.example.com", tools: [] })).toBeNull()
    expect(resolveMcpOAuthAudience({ id: "x", transport: "stdio", command: "node", tools: [] })).toBeNull()
  })

  it("rejects tokenish args to a remote server without audience (no passthrough)", () => {
    const bare = { id: "x", transport: "http", url: "https://api.example.com", tools: [] }
    expect(rejectMcpTokenPassthrough(bare, { query: "hi" })).toEqual({ ok: true })
    expect(rejectMcpTokenPassthrough(bare, { token: "sekrit" })).toMatchObject({ ok: false })
    expect(rejectMcpTokenPassthrough(bare, { api_key: "k" })).toMatchObject({ ok: false })
  })

  it("allows tokenish args once an explicit oauthAudience is bound", () => {
    const bound = { id: "x", transport: "sse", url: "https://mcp.example.com/sse", oauthAudience: "mcp.example.com", tools: [] }
    expect(rejectMcpTokenPassthrough(bound, { token: "aud-bound" })).toEqual({ ok: true })
  })
})

describe("mcp tool capability", () => {
  it("normalizes capability names", () => {
    expect(toMcpCapabilityName("search")).toBe("mcp_search")
    expect(toMcpCapabilityName("mcp_echo")).toBe("mcp_echo")
    expect(parseMcpCapability("mcp_fetch")).toEqual({
      capability: "mcp_fetch",
      toolName: "fetch",
    })
  })

  it("matches MCP grant scope by server and tool", () => {
    expect(normalizeMcpGrantScope({ serverId: "My-Server", toolName: "search" })).toEqual({
      serverId: "my-server",
      toolName: "search",
    })
    const scope = {
      capabilities: ["mcp_search"],
      digest: "d1",
      mcp: { serverId: "my-server", toolName: "search" },
      network: "allow" as const,
    }
    expect(
      grantScopeMatchesMcpTool(scope, { capability: "mcp_search", toolName: "search" }),
    ).toBe(true)
    expect(
      grantScopeMatchesMcpTool(scope, { capability: "mcp_fetch", toolName: "fetch" }),
    ).toBe(false)
    expect(scopedGrantScopeTargetsMcpServer(scope, "my-server")).toBe(true)
    expect(scopedGrantScopeTargetsMcpServer(scope, "other")).toBe(false)
  })

  it("allows legacy grants without mcp block", () => {
    const scope = {
      capabilities: ["mcp_search"],
      digest: "d1",
      network: "allow" as const,
    }
    expect(
      grantScopeMatchesMcpTool(scope, { capability: "mcp_search", toolName: "search" }),
    ).toBe(true)
    expect(scopedGrantScopeTargetsMcpServer(scope, "any")).toBe(false)
  })

  it("exposes default provider metadata skeleton", () => {
    expect(defaultMcpProviderMetadata("Demo")).toEqual({
      serverId: "demo",
      defaultRisk: "high",
      defaultSandboxProfile: "workspace-write-network-deny",
      auditPolicy: "summary",
    })
  })

  it("reads provider metadata from manifest server defaults", () => {
    expect(
      mcpProviderMetadataFromManifest({
        serverId: "github",
        defaultRisk: "low",
        auditPolicy: "full",
        defaultSandboxProfile: "workspace-write-network-allowlist",
      }),
    ).toEqual({
      serverId: "github",
      defaultRisk: "low",
      defaultSandboxProfile: "workspace-write-network-allowlist",
      auditPolicy: "full",
    })
  })

  it("parses namespaced capabilities with server ids", () => {
    expect(parseMcpCapability("mcp_firecrawl_firecrawl_scrape", ["firecrawl", "github"])).toEqual({
      capability: "mcp_firecrawl_firecrawl_scrape",
      serverId: "firecrawl",
      toolName: "firecrawl_scrape",
    })
    expect(toMcpCapabilityNameForServer("firecrawl", "firecrawl_scrape")).toBe(
      "mcp_firecrawl_firecrawl_scrape",
    )
  })
})

describe("capability normalization (P3 MCP)", () => {
  it("defines the capability prefix", () => {
    expect(MCP_CAPABILITY_PREFIX).toBe("mcp_")
  })

  it("isMcpCapability matches the mcp_ prefix only", () => {
    expect(isMcpCapability("mcp_git_read_file")).toBe(true)
    expect(isMcpCapability("mcp_")).toBe(true)
    expect(isMcpCapability("read_file")).toBe(false)
    expect(isMcpCapability("")).toBe(false)
  })

  it("normalizes mcp server id (trim + lowercase)", () => {
    expect(normalizeMcpServerId("  MyGit  ")).toBe("mygit")
    expect(normalizeMcpServerId("FS.Server")).toBe("fs.server")
  })

  it("normalizes mcp tool name (trim only, case preserved)", () => {
    expect(normalizeMcpToolName("  read_file ")).toBe("read_file")
  })

  it("resolveMcpServerIdFromCapability resolves the namespaced server id", () => {
    expect(resolveMcpServerIdFromCapability("mcp_git_read_file", ["git"])).toBe("git")
    expect(resolveMcpServerIdFromCapability("mcp_git_read_file", ["Other", "git"])).toBe("git")
  })

  it("returns undefined when no server matches or capability is not mcp_", () => {
    expect(resolveMcpServerIdFromCapability("mcp_unknown_tool", ["git"])).toBeUndefined()
    expect(resolveMcpServerIdFromCapability("read_file", ["git"])).toBeUndefined()
  })
})
