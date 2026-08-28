/**
 * LLM JSON decoder — Application-layer bridge from model protocol output to the
 * Domain ModelDecision ADT (DESIGN §6.2). Robust to common LLM JSON deviations
 * (markdown fences, trailing commas, single quotes, embedded objects).
 */
import type { DecodeResult, ModelDecision } from "@butler/domain/runtime.js"

export type { DecodeResult, ModelDecision } from "@butler/domain/runtime.js"

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function parseModelDecisionObject(obj: Record<string, unknown>): DecodeResult {
  const tag = obj["_tag"]
  switch (tag) {
    case "Respond": {
      const content = obj["content"]
      if (typeof content !== "string")
        return { ok: false, reason: "Respond.content must be string" }
      return { ok: true, value: { _tag: "Respond", content } }
    }
    case "CallCapability": {
      const name = obj["name"]
      const args = obj["arguments"]
      if (typeof name !== "string")
        return { ok: false, reason: "CallCapability.name must be string" }
      if (!args || typeof args !== "object" || Array.isArray(args)) {
        return { ok: false, reason: "CallCapability.arguments must be object" }
      }
      const callId = obj["callId"]
      const decision: ModelDecision =
        typeof callId === "string"
          ? { _tag: "CallCapability", name, arguments: args as Record<string, unknown>, callId }
          : { _tag: "CallCapability", name, arguments: args as Record<string, unknown> }
      return { ok: true, value: decision }
    }
    case "StartChildRun": {
      const role = obj["role"]
      const objective = obj["objective"]
      if (typeof role !== "string")
        return { ok: false, reason: "StartChildRun.role must be string" }
      if (typeof objective !== "string")
        return { ok: false, reason: "StartChildRun.objective must be string" }
      const grantsRaw = obj["grants"]
      const grants =
        Array.isArray(grantsRaw) && grantsRaw.every((g) => typeof g === "string")
          ? (grantsRaw as readonly string[])
          : undefined
      const decision: ModelDecision =
        grants !== undefined
          ? { _tag: "StartChildRun", role, objective, grants }
          : { _tag: "StartChildRun", role, objective }
      return { ok: true, value: decision }
    }
    case "WaitForApproval": {
      const question = obj["question"]
      if (typeof question !== "string")
        return { ok: false, reason: "WaitForApproval.question must be string" }
      return { ok: true, value: { _tag: "WaitForApproval", question } }
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
  if (!isRecord(parsed)) {
    return { ok: false, reason: "not an object" }
  }
  return parseModelDecisionObject(parsed)
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

function unwrapMarkdownFence(text: string): string | null {
  const m = text.match(/```(?:json|JSON)?[ \t]*\r?\n?([\s\S]*?)(?:```|$)/)
  if (!m) return null
  const inner = (m[1] ?? "").trim()
  return inner.length === 0 || inner === text ? null : inner
}

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
        continue
      }
    }
    out += ch
  }
  return out
}

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

function repairCandidates(text: string): readonly string[] {
  const base = [text]
  const fenced = unwrapMarkdownFence(text)
  if (fenced !== null) base.push(fenced)
  const out: string[] = []
  for (const v of base) {
    const commaFixed = stripTrailingCommas(v)
    if (commaFixed !== v) out.push(commaFixed)
  }
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

  for (const repaired of repairCandidates(trimmed)) {
    const decoded = tryDecode(repaired)
    if (decoded) return decoded
  }

  return decodeDecisionJson(trimmed)
}
