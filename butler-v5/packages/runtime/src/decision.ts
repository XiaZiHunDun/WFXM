export type ModelDecision =
  | { readonly _tag: "Respond"; readonly content: string }
  | { readonly _tag: "CallTool"; readonly toolName: string; readonly args: Record<string, unknown> }
  | { readonly _tag: "Delegate"; readonly role: string; readonly task: string }
  | { readonly _tag: "AskApproval"; readonly question: string }
  | { readonly _tag: "Finish"; readonly reason: string }

export type DecodeResult =
  | { readonly ok: true; readonly value: ModelDecision }
  | { readonly ok: false; readonly reason: string }

function parseModelDecisionObject(obj: Record<string, unknown>): DecodeResult {
  const tag = obj["_tag"]
  switch (tag) {
    case "Respond": {
      const content = obj["content"]
      if (typeof content !== "string")
        return { ok: false, reason: "Respond.content must be string" }
      return { ok: true, value: { _tag: "Respond", content } }
    }
    case "CallTool": {
      const toolName = obj["toolName"]
      const args = obj["args"]
      if (typeof toolName !== "string")
        return { ok: false, reason: "CallTool.toolName must be string" }
      if (!args || typeof args !== "object" || Array.isArray(args)) {
        return { ok: false, reason: "CallTool.args must be object" }
      }
      return {
        ok: true,
        value: { _tag: "CallTool", toolName, args: args as Record<string, unknown> },
      }
    }
    case "Delegate": {
      const role = obj["role"]
      const task = obj["task"]
      if (typeof role !== "string") return { ok: false, reason: "Delegate.role must be string" }
      if (typeof task !== "string") return { ok: false, reason: "Delegate.task must be string" }
      return { ok: true, value: { _tag: "Delegate", role, task } }
    }
    case "AskApproval": {
      const question = obj["question"]
      if (typeof question !== "string")
        return { ok: false, reason: "AskApproval.question must be string" }
      return { ok: true, value: { _tag: "AskApproval", question } }
    }
    case "Finish": {
      const reason = obj["reason"]
      if (typeof reason !== "string") return { ok: false, reason: "Finish.reason must be string" }
      return { ok: true, value: { _tag: "Finish", reason } }
    }
    default:
      return { ok: false, reason: `unknown tag: ${String(tag)}` }
  }
}

function decodeDecisionJson(text: string): DecodeResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { ok: false, reason: "invalid JSON" }
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, reason: "not an object" }
  }
  return parseModelDecisionObject(parsed as Record<string, unknown>)
}

/** Extract `{...}` objects that look like ModelDecision payloads from mixed LLM text. */
export function extractEmbeddedDecisionJson(raw: string): readonly string[] {
  const found: string[] = []
  for (let i = 0; i < raw.length; i++) {
    if (raw[i] !== "{") continue
    let depth = 0
    let inString = false
    let escaped = false
    for (let j = i; j < raw.length; j++) {
      const ch = raw[j]
      if (inString) {
        if (escaped) {
          escaped = false
          continue
        }
        if (ch === "\\") {
          escaped = true
          continue
        }
        if (ch === '"') inString = false
        continue
      }
      if (ch === '"') {
        inString = true
        continue
      }
      if (ch === "{") depth += 1
      else if (ch === "}") {
        depth -= 1
        if (depth === 0) {
          const slice = raw.slice(i, j + 1)
          if (slice.includes('"_tag"')) found.push(slice)
          break
        }
      }
    }
  }
  return found
}

/**
 * 尝试解码直接 JSON；失败再尝试从文本中抽取嵌入的 `{...}` 决策对象。
 * 返回 null 表示两者都未解出。
 */
function tryDecode(text: string): DecodeResult | null {
  const direct = decodeDecisionJson(text)
  if (direct.ok) return direct
  const embedded = extractEmbeddedDecisionJson(text)
  for (let i = embedded.length - 1; i >= 0; i--) {
    const candidate = embedded[i]
    if (!candidate) continue
    const decoded = decodeDecisionJson(candidate)
    if (decoded.ok) return decoded
  }
  return null
}

/** 剥离 markdown 代码围栏（```json ... ```），返回围栏内内容；无围栏返回 null。 */
function unwrapMarkdownFence(text: string): string | null {
  const m = text.match(/```(?:json|JSON)?[ \t]*\r?\n?([\s\S]*?)(?:```|$)/)
  if (!m) return null
  const inner = (m[1] ?? "").trim()
  return inner.length === 0 || inner === text ? null : inner
}

/** 字符串感知地移除对象/数组末尾的尾逗号（LLM 常见输出偏差）。 */
function stripTrailingCommas(text: string): string {
  let out = ""
  let inString = false
  let escaped = false
  for (let i = 0; i < text.length; i++) {
    const ch = text.charAt(i)
    if (inString) {
      out += ch
      if (escaped) escaped = false
      else if (ch === "\\") escaped = true
      else if (ch === '"') inString = false
      continue
    }
    if (ch === '"') {
      inString = true
      out += ch
      continue
    }
    if (ch === ",") {
      let j = i + 1
      while (j < text.length && /\s/.test(text.charAt(j))) j++
      if (j < text.length && (text.charAt(j) === "}" || text.charAt(j) === "]")) {
        continue // 丢弃尾逗号
      }
    }
    out += ch
  }
  return out
}

/**
 * 单引号 JSON → 双引号（保守：仅在调用方确认全文不含双引号时使用，避免混合引号误判）。
 * 字符串内的 `\'` 还原为 `'`（双引号串内无需转义），字面换行转义为 `\n`。
 */
function repairSingleQuotes(text: string): string {
  let out = ""
  let inString = false
  let escaped = false
  for (const ch of text) {
    if (escaped) {
      out += ch === "'" ? "'" : "\\" + ch
      escaped = false
      continue
    }
    if (ch === "\\") {
      escaped = true
      continue
    }
    if (ch === "'") {
      inString = !inString
      out += '"'
      continue
    }
    if (inString) {
      if (ch === "\n") out += "\\n"
      else if (ch === "\r") out += "\\r"
      else if (ch === "\t") out += "\\t"
      else out += ch
      continue
    }
    out += ch
  }
  return out
}

/** 生成容错修复候选（原始 → 围栏剥离 → 尾逗号 → 单引号），与原文本不同才保留。 */
function repairCandidates(text: string): readonly string[] {
  const base = [text]
  const fenced = unwrapMarkdownFence(text)
  if (fenced !== null) base.push(fenced)
  const out: string[] = []
  for (const v of base) {
    const commaFixed = stripTrailingCommas(v)
    if (commaFixed !== v) out.push(commaFixed)
  }
  // 单引号修复仅当全文不含双引号时尝试（避免混合引号产生误判）。
  if (!text.includes('"')) {
    const singleFixed = repairSingleQuotes(text)
    if (singleFixed !== text) out.push(singleFixed)
  }
  return out
}

export function decodeDecision(raw: string): DecodeResult {
  const trimmed = raw.trim()
  const direct = tryDecode(trimmed)
  if (direct) return direct

  // 容错修复阶梯：markdown 围栏 / 尾逗号 / 单引号，逐个尝试解码。
  for (const repaired of repairCandidates(trimmed)) {
    const decoded = tryDecode(repaired)
    if (decoded) return decoded
  }

  // 全部失败：保底返回最初解析的错误原因（如 unknown tag / invalid JSON）。
  return decodeDecisionJson(trimmed)
}
