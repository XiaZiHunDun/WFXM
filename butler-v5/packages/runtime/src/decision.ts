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

export function decodeDecision(raw: string): DecodeResult {
  const trimmed = raw.trim()
  const direct = decodeDecisionJson(trimmed)
  if (direct.ok) return direct

  const embedded = extractEmbeddedDecisionJson(trimmed)
  for (let i = embedded.length - 1; i >= 0; i--) {
    const candidate = embedded[i]
    if (!candidate) continue
    const decoded = decodeDecisionJson(candidate)
    if (decoded.ok) return decoded
  }

  return direct
}
