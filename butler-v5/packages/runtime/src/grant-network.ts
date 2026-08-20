import { WECHAT_OUTBOUND_NETWORK_HOSTS } from "@butler/domain/governance/wechat-network-hosts.js"

/** Network hosts written into ScopedGrant when approving outbound capabilities. */
export function outboundNetworkHostsForCapability(capability: string): readonly string[] | undefined {
  if (capability === "send_wechat_file") {
    return WECHAT_OUTBOUND_NETWORK_HOSTS
  }
  return undefined
}
