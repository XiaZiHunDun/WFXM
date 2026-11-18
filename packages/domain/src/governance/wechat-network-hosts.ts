/** WeChat CDN / iLink hosts allowed for outbound media (Grant networkHosts SSOT). */
export const WECHAT_OUTBOUND_NETWORK_HOSTS: readonly string[] = [
  "novac2c.cdn.wechat.qq.com",
  "novac2c.cdn.weixin.qq.com",
  "ilinkai.wechat.qq.com",
  "ilinkai.weixin.qq.com",
  "wx.qlogo.cn",
  "thirdwx.qlogo.cn",
  "res.wx.qq.com",
  "mmbiz.qpic.cn",
  "mmbiz.qlogo.cn",
]

export const WECHAT_OUTBOUND_NETWORK_HOST_SET: ReadonlySet<string> = new Set(
  WECHAT_OUTBOUND_NETWORK_HOSTS,
)
