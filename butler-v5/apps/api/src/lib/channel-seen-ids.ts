/**
 * D74 T4 (audit #20 SEC-001): per-process dedup cache for channel
 * inbound message_ids. Telegram (and future channels like Signal /
 * Discord) sign their webhook bodies to prevent UNAUTHORIZED access
 * but NOT to prevent REPLAY: an attacker who captures one signed
 * update can replay it indefinitely until the bot-token rotates.
 *
 * Without dedup, each replay triggers handleChannelInbound →
 * runButlerLoop → full LLM/tool-call cycle + appendAuditEvent writes.
 *
 * Pattern mirrors ilink-poller.ts:145-156 (in production since D62)
 * and adds TTL=10min + 10K cap (audit fix_hint) so the cache stays
 * bounded. Returns true on FIRST sight, false on duplicate — caller
 * returns HTTP 204 (idempotent semantics, same as D63 T4 style).
 *
 * Module-scoped state means a multi-process deployment would have
 * per-process caches (not global). A leaked-bot-token attacker could
 * bypass by distributing replays across processes. For single-process
 * deployments (current default), this closes the documented vector.
 */

const TTL_MS = 10 * 60 * 1000
const CAP = 10_000

interface SeenEntry {
  readonly ts: number
}

const seen: Map<string, SeenEntry> = new Map()

/**
 * Records (channelId, messageId) as seen and returns true on first
 * sight, false on duplicate (within TTL window).
 */
export function markChannelSeen(
  channelId: string,
  messageId: string,
): boolean {
  const key = `${channelId}:${messageId}`
  const now = Date.now()
  const existing = seen.get(key)
  if (existing && now - existing.ts < TTL_MS) {
    return false
  }
  seen.set(key, { ts: now })
  // Evict oldest entries when over CAP (insertion-order Map).
  if (seen.size > CAP) {
    const overflow = seen.size - CAP
    const iter = seen.keys()
    for (let i = 0; i < overflow; i++) {
      const next = iter.next()
      if (next.done) break
      seen.delete(next.value)
    }
  }
  return true
}

/** Test-only — reset the cache between tests. */
export function _resetChannelSeenForTest(): void {
  seen.clear()
}