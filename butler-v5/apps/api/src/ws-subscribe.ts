import { randomBytes } from "node:crypto"

const DEFAULT_SUBSCRIBE_TTL_MS = 3_600_000
// D63 T4 (audit #9 F-14): cap the in-memory token store. Without a cap,
// an unauthenticated /v1/ws/subscribe endpoint (F-05 sibling) lets a
// network-reachable attacker issue unbounded tokens and consume memory
// until OOM. 10K tokens × ~64 bytes/token ≈ 640 KB, well within the
// process memory budget. Hard cap on issuance: prune oldest when at cap.
const MAX_TOKENS = 10_000

export type SubscribeRecord = {
  readonly conversationId: string
  readonly expiresAtMs: number
}

const tokens = new Map<string, SubscribeRecord>()

function pruneExpired(nowMs: number): void {
  for (const [token, rec] of tokens) {
    if (rec.expiresAtMs <= nowMs) {
      tokens.delete(token)
    }
  }
}

export function issueSubscribeToken(
  conversationId: string,
  opts: { readonly ttlMs?: number; readonly nowMs?: number } = {},
): { readonly token: string; readonly expiresAtMs: number } | null {
  const nowMs = opts.nowMs ?? Date.now()
  pruneExpired(nowMs)
  // Enforce cap by pruning oldest entries first. Map iteration order is
  // insertion order, so the front of the map is the oldest token. If
  // still at cap after pruning, refuse (caller should surface 503).
  while (tokens.size >= MAX_TOKENS) {
    const oldest = tokens.keys().next().value
    if (oldest === undefined) break
    tokens.delete(oldest)
  }
  if (tokens.size >= MAX_TOKENS) return null
  const ttlMs = opts.ttlMs ?? DEFAULT_SUBSCRIBE_TTL_MS
  const token = randomBytes(24).toString("base64url")
  const expiresAtMs = nowMs + ttlMs
  tokens.set(token, { conversationId, expiresAtMs })
  return { token, expiresAtMs }
}

export function lookupSubscribeToken(
  token: string,
  opts: { readonly nowMs?: number } = {},
): SubscribeRecord | undefined {
  const nowMs = opts.nowMs ?? Date.now()
  pruneExpired(nowMs)
  return tokens.get(token)
}

export function clearSubscribeTokens(): void {
  tokens.clear()
}
