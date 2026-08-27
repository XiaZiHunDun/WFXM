import { describe, expect, it } from "vitest"
import { decodeDecision } from "./decision.js"

describe("decodeDecision", () => {
  it("decodes a valid Respond JSON", () => {
    const out = decodeDecision('{"_tag":"Respond","content":"hello"}')
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "Respond") expect(out.value.content).toBe("hello")
  })

  it("decodes a valid CallTool JSON", () => {
    const out = decodeDecision('{"_tag":"CallTool","toolName":"read_file","args":{"path":"/ws"}}')
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallTool") expect(out.value.toolName).toBe("read_file")
  })

  it("decodes a valid Delegate JSON", () => {
    const out = decodeDecision('{"_tag":"Delegate","role":"researcher","task":"find docs"}')
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "Delegate") expect(out.value.role).toBe("researcher")
  })

  it("decodes a valid AskApproval JSON", () => {
    const out = decodeDecision('{"_tag":"AskApproval","question":"ok?"}')
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "AskApproval") expect(out.value.question).toBe("ok?")
  })

  it("decodes a valid Finish JSON", () => {
    const out = decodeDecision('{"_tag":"Finish","reason":"done"}')
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "Finish") expect(out.value.reason).toBe("done")
  })

  it("rejects unknown tag", () => {
    const out = decodeDecision('{"_tag":"SelfDestruct","content":"x"}')
    expect(out.ok).toBe(false)
    if (!out.ok) expect(out.reason).toMatch(/unknown tag/i)
  })

  it("rejects malformed JSON", () => {
    const out = decodeDecision("not json")
    expect(out.ok).toBe(false)
    if (!out.ok) expect(out.reason).toMatch(/JSON/i)
  })

  it("rejects non-object payload", () => {
    const out = decodeDecision('"just a string"')
    expect(out.ok).toBe(false)
  })

  it("rejects Respond with missing content", () => {
    const out = decodeDecision('{"_tag":"Respond"}')
    expect(out.ok).toBe(false)
  })

  it("accepts extra fields (forward compat)", () => {
    const out = decodeDecision('{"_tag":"Respond","content":"x","future":42}')
    expect(out.ok).toBe(true)
  })

  it("extracts embedded JSON from prose + decision object", () => {
    const mixed = [
      "I'll write that file for you.",
      "",
      '{"_tag":"CallTool","toolName":"write_file","args":{"path":"a.txt","content":"hi"}}',
    ].join("\n")
    const out = decodeDecision(mixed)
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallTool") {
      expect(out.value.toolName).toBe("write_file")
    }
  })

  it("decodes JSON wrapped in markdown code fence", () => {
    const fenced = "```json\n{\"_tag\":\"CallTool\",\"toolName\":\"read_file\",\"args\":{}}\n```"
    const out = decodeDecision(fenced)
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallTool") expect(out.value.toolName).toBe("read_file")
  })

  it("decodes JSON with trailing commas (LLM deviation)", () => {
    const trailing = '{"_tag":"CallTool","toolName":"read_file","args":{"path":"/ws",},}'
    const out = decodeDecision(trailing)
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallTool") {
      expect(out.value.toolName).toBe("read_file")
      expect((out.value.args as { path?: unknown }).path).toBe("/ws")
    }
  })

  it("decodes single-quoted JSON payload", () => {
    const out = decodeDecision("{'_tag': 'Respond', 'content': 'hi'}")
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "Respond") expect(out.value.content).toBe("hi")
  })

  it("decodes single-quoted JSON with escaped apostrophe in content", () => {
    const out = decodeDecision("{'_tag': 'Respond', 'content': 'it\\'s fine'}")
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "Respond") expect(out.value.content).toBe("it's fine")
  })

  it("preserves failure reason when repairs cannot recover", () => {
    const out = decodeDecision('{"_tag":"SelfDestruct","content":"x"}')
    expect(out.ok).toBe(false)
    if (!out.ok) expect(out.reason).toMatch(/unknown tag/i)
  })
})
