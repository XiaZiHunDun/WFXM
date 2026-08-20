import { describe, expect, it } from "vitest"
import { outboundNetworkHostsForCapability } from "./grant-network.js"

describe("outboundNetworkHostsForCapability", () => {
  it("returns WeChat CDN hosts for send_wechat_file", () => {
    const hosts = outboundNetworkHostsForCapability("send_wechat_file")
    expect(hosts).toBeDefined()
    expect(hosts).toContain("novac2c.cdn.weixin.qq.com")
  })

  it("returns undefined for non-outbound capabilities", () => {
    expect(outboundNetworkHostsForCapability("read_file")).toBeUndefined()
  })
})
