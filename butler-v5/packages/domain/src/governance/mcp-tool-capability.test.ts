import { describe, expect, it } from "vitest"
import {
  defaultMcpProviderMetadata,
  grantScopeMatchesMcpTool,
  normalizeMcpGrantScope,
  parseMcpCapability,
  scopedGrantScopeTargetsMcpServer,
  toMcpCapabilityName,
  toMcpCapabilityNameForServer,
} from "./mcp-tool-capability.js"

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
