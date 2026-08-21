import { describe, expect, it } from "vitest"
import {
  mergeGrantNetworkHosts,
  mcpServerHostnameFromEnv,
  parseGrantNetworkHostsFromEnv,
  resolveGrantNetworkHosts,
} from "./grant-network-hosts.js"

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
