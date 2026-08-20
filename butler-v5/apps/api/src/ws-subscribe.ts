import { randomBytes } from "node:crypto"

export const DEFAULT_SUBSCRIBE_TTL_MS = 3_600_000

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
): { readonly token: string; readonly expiresAtMs: number } {
  const nowMs = opts.nowMs ?? Date.now()
  pruneExpired(nowMs)
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
