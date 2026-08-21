import { describe, expect, it } from "vitest"
import { outboundNetworkHostsForCapability } from "./grant-network.js"

describe("outboundNetworkHostsForCapability", () => {
  it("returns WeChat CDN hosts for send_wechat_file", () => {
    const hosts = outboundNetworkHostsForCapability("send_wechat_file")
    expect(hosts).toBeDefined()
    expect(hosts).toContain("novac2c.cdn.weixin.qq.com")
  })

  it("merges extra env hosts for send_wechat_file", () => {
    const hosts = outboundNetworkHostsForCapability("send_wechat_file", {
      BUTLER_V5_GRANT_NETWORK_HOSTS: "proxy.internal",
    })
    expect(hosts).toContain("proxy.internal")
    expect(hosts).toContain("novac2c.cdn.weixin.qq.com")
  })

  it("returns MCP server hostname for mcp capabilities", () => {
    expect(
      outboundNetworkHostsForCapability("mcp_search", {
        BUTLER_V5_MCP_URL: "https://mcp.example.com/rpc",
      }),
    ).toEqual(["mcp.example.com"])
  })

  it("returns undefined for non-outbound capabilities", () => {
    expect(outboundNetworkHostsForCapability("read_file")).toBeUndefined()
  })
})
