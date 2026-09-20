/**
 * D74 T3 (audit #20 CQ-009): extract detectSpam heuristics from
 * wechat-inbound-butler.ts into a dedicated module. Each detector
 * returns a user-facing reason string when the content fails, or null
 * when it looks normal. detectSpam becomes a thin orchestrator.
 *
 * Heuristics preserved verbatim from the original inline implementation
 * (P2 batch 2026-09-04 + P2 batch v2 2026-09-08):
 *   F1 — max length (MAX_SPAM_CHARS)
 *   F2 — repeated character (CJK per-char count + 30% dominance)
 *   F3 — emoji ratio (0x1f000-0x1ffff range)
 *   F4 — per-line repeat ratio
 *   F5 — whitespace-token repeat
 *   F6 — length+structure (1500-2000 chars, no newlines, <0.5% punct)
 */

export const MAX_SPAM_CHARS = 2000
const REPEAT_TOKEN_THRESHOLD = 30
const EMOJI_RATIO_MAX = 0.6
const MIN_LINE_REPEAT_TOTAL = 10
const LINE_REPEAT_RATIO_MAX = 0.3
const MIN_TOKEN_REPEAT_TOTAL = 10
const TOKEN_REPEAT_THRESHOLD = 20
const TOKEN_REPEAT_RATIO_MAX = 0.3
const STRUCTURE_MIN_LEN = 1500
const STRUCTURE_MAX_LEN = 2000
const STRUCTURE_PUNCT_RATIO_MAX = 0.005
const STRUCTURE_PUNCT_REGEX = /[。，！？；：、,.!?;:]/

export function hasExcessiveLength(content: string): string | null {
  if (content.length > MAX_SPAM_CHARS) {
    return `消息过长（${content.length} 字符，上限 ${MAX_SPAM_CHARS}）。请发具体需求。`
  }
  return null
}

/**
 * Repeated-character detector (F2). Catches "请帮我请帮我请帮我..."
 * spam while not flagging legitimate long Chinese messages (counts each
 * character; dominates only if > threshold AND >= 30% of total).
 */
export function hasRepeatedCharacter(content: string): string | null {
  if (content.length < 50) return null
  const charCounts = new Map<string, number>()
  for (const ch of content) charCounts.set(ch, (charCounts.get(ch) ?? 0) + 1)
  let maxChar = ""
  let maxCount = 0
  for (const [c, n] of charCounts) {
    if (n > maxCount) {
      maxCount = n
      maxChar = c
    }
  }
  if (maxCount > REPEAT_TOKEN_THRESHOLD && maxCount / content.length >= 0.3) {
    return `检测到字符「${maxChar}」重复 ${maxCount} 次。请发具体需求。`
  }
  return null
}

export function hasExcessiveEmojiRatio(content: string): string | null {
  if (content.length < 20) return null
  let emojiCount = 0
  for (const ch of content) {
    const code = ch.codePointAt(0) ?? 0
    if (code >= 0x1f000 && code <= 0x1ffff) emojiCount += 1
  }
  if (emojiCount / content.length > EMOJI_RATIO_MAX) {
    return `检测到 emoji 占比 ${Math.round((emojiCount / content.length) * 100)}%。请发具体需求。`
  }
  return null
}

/** F3: per-line repeat (multi-line short-line spam). */
export function hasRepeatedLines(content: string): string | null {
  if (content.length < 100) return null
  const lines = content.split(/\r?\n/).filter((l) => l.length > 0)
  if (lines.length < MIN_LINE_REPEAT_TOTAL) return null
  const unique = new Set(lines)
  if (unique.size / lines.length < LINE_REPEAT_RATIO_MAX) {
    return `检测到 ${lines.length} 行中只有 ${unique.size} 种，疑似重复内容。请发具体需求。`
  }
  return null
}

/** F4: whitespace-token repeat (multi-word spam). */
export function hasRepeatedTokens(content: string): string | null {
  if (content.length < 50) return null
  const tokens = content.split(/\s+/).filter((t) => t.length > 0)
  if (tokens.length < MIN_TOKEN_REPEAT_TOTAL) return null
  const counts = new Map<string, number>()
  for (const t of tokens) counts.set(t, (counts.get(t) ?? 0) + 1)
  let maxToken = ""
  let maxCount = 0
  for (const [t, n] of counts) {
    if (n > maxCount) {
      maxCount = n
      maxToken = t
    }
  }
  if (
    maxCount > TOKEN_REPEAT_THRESHOLD &&
    maxCount / tokens.length >= TOKEN_REPEAT_RATIO_MAX
  ) {
    const display = maxToken.length > 20 ? `${maxToken.slice(0, 20)}...` : maxToken
    return `检测到 token「${display}」重复 ${maxCount} 次。请发具体需求。`
  }
  return null
}

/** F5: length + structure (1500-2000 chars, no newlines, very low punctuation). */
export function hasAbnormalStructure(content: string): string | null {
  if (content.length <= STRUCTURE_MIN_LEN || content.length > STRUCTURE_MAX_LEN) {
    return null
  }
  if (content.includes("\n")) return null
  let punctCount = 0
  for (const ch of content) if (STRUCTURE_PUNCT_REGEX.test(ch)) punctCount += 1
  if (punctCount / content.length < STRUCTURE_PUNCT_RATIO_MAX) {
    return `消息结构异常（${content.length} 字符无标点无换行）。请分批发送或简化需求。`
  }
  return null
}