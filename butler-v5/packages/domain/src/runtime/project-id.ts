/**
 * Derive a stable project key from a conversation stream id.
 * Matches intake conventions: WeChat `c-{project}-{user}`, channel `c-ch-{channel}-{subject}`, CLI `cli-*`.
 */
export function inferProjectIdFromConversationId(conversationId: string): string {
  const id = conversationId.trim()
  if (id.length === 0) return "_default"
  if (id.startsWith("cli-")) return "cli"
  if (id.startsWith("c-ch-")) {
    const rest = id.slice("c-ch-".length)
    const dash = rest.indexOf("-")
    const channel = dash >= 0 ? rest.slice(0, dash) : rest
    return channel.length > 0 ? `channel:${channel}` : "channel:unknown"
  }
  if (id.startsWith("c-")) {
    const rest = id.slice(2)
    const dash = rest.indexOf("-")
    if (dash > 0) return rest.slice(0, dash)
  }
  return "_default"
}
