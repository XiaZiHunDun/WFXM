import { WECHAT_OUTBOUND_NETWORK_HOSTS } from "@butler/domain/governance/wechat-network-hosts.js"
import { resolveGrantNetworkHosts } from "@butler/domain/governance/grant-network-hosts.js"

/** Network hosts written into ScopedGrant when approving outbound capabilities. */
export function outboundNetworkHostsForCapability(
  capability: string,
  env: NodeJS.ProcessEnv = process.env,
): readonly string[] | undefined {
  return resolveGrantNetworkHosts({
    capability,
    wechatHosts: WECHAT_OUTBOUND_NETWORK_HOSTS,
    env,
  })
}
