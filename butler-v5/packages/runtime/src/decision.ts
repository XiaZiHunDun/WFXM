export type ModelDecision =
  | { readonly _tag: "Respond"; readonly content: string }
  | { readonly _tag: "CallTool"; readonly toolName: string; readonly args: Record<string, unknown> }
  | { readonly _tag: "Delegate"; readonly role: string; readonly task: string }
  | { readonly _tag: "AskApproval"; readonly question: string }
  | { readonly _tag: "Finish"; readonly reason: string }

export type DecodeResult =
  | { readonly ok: true; readonly value: ModelDecision }
  | { readonly ok: false; readonly reason: string }

export function decodeDecision(raw: string): DecodeResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ok: false, reason: "invalid JSON" }
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, reason: "not an object" }
  }
  const obj = parsed as Record<string, unknown>
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
