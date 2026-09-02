import { describe, expect, it } from "vitest"
import {
  mergeGrantNetworkHosts,
  mcpServerHostnameFromEnv,
  parseGrantNetworkHostsFromEnv,
  resolveGrantNetworkHosts,
} from "./grant-network-hosts.js"
import { hostnameFromHttpUrl, mcpCapabilityOutboundHosts } from "./grant-network-hosts.js"

describe("grant network hosts", () => {
  it("parses extra hosts from env", () => {
    expect(
      parseGrantNetworkHostsFromEnv({
        BUTLER_V5_GRANT_NETWORK_HOSTS: "api.example.com, Slack.com",
      }),
    ).toEqual(["api.example.com", "slack.com"])
  })

  it("merges MCP server hostname with extras", () => {
    const hosts = resolveGrantNetworkHosts({
      capability: "mcp_search",
      env: {
        BUTLER_V5_MCP_URL: "https://mcp.internal:8443/rpc",
        BUTLER_V5_GRANT_NETWORK_HOSTS: "cdn.example.com",
      },
    })
    expect(hosts).toEqual(["mcp.internal", "cdn.example.com"])
  })

  it("adds Todoist outbound host for todoist MCP capabilities", () => {
    const hosts = resolveGrantNetworkHosts({
      capability: "mcp_todoist_lst-projects",
      env: {},
    })
    expect(hosts).toEqual(["api.todoist.com"])
  })

  it("adds Firecrawl outbound host for firecrawl MCP capabilities", () => {
    expect(
      resolveGrantNetworkHosts({
        capability: "mcp_firecrawl_firecrawl_scrape",
        env: {},
      }),
    ).toEqual(["api.firecrawl.dev"])
  })

  it("adds GitHub outbound host for github MCP capabilities", () => {
    expect(
      resolveGrantNetworkHosts({
        capability: "mcp_github_search_repositories",
        env: {},
      }),
    ).toEqual(["api.github.com"])
  })

  it("returns undefined when no hosts configured for read_file", () => {
    expect(resolveGrantNetworkHosts({ capability: "read_file", env: {} })).toBeUndefined()
  })

  it("extracts MCP hostname from env", () => {
    expect(
      mcpServerHostnameFromEnv({ BUTLER_V5_MCP_URL: "http://127.0.0.1:7777/mcp" }),
    ).toBe("127.0.0.1")
  })

  it("deduplicates merged hosts", () => {
    expect(mergeGrantNetworkHosts(["A.com", "a.com"], ["b.com"])).toEqual(["a.com", "b.com"])
  })
})

describe("grant network host helpers", () => {
  it("extracts a lowercase hostname from an http url", () => {
    expect(hostnameFromHttpUrl("https://API.Example.COM/path?q=1")).toBe("api.example.com")
    expect(hostnameFromHttpUrl("http://foo.bar:8080/x")).toBe("foo.bar")
    expect(hostnameFromHttpUrl("   ")).toBeUndefined()
    expect(hostnameFromHttpUrl("not a url")).toBeUndefined()
  })

  it("derives outbound hosts for known mcp capability prefixes", () => {
    expect(mcpCapabilityOutboundHosts("mcp_github_get_repo")).toEqual(["api.github.com"])
    expect(mcpCapabilityOutboundHosts("mcp_todoist_list_tasks")).toEqual(["api.todoist.com"])
    expect(mcpCapabilityOutboundHosts("mcp_firecrawl_crawl")).toEqual(["api.firecrawl.dev"])
    expect(mcpCapabilityOutboundHosts("mcp_unknown_x")).toBeUndefined()
    expect(mcpCapabilityOutboundHosts("read_file")).toBeUndefined()
  })
})
