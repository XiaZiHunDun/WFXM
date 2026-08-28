import { describe, expect, it } from "vitest"
import { decodeDecision } from "./decision.js"

describe("decodeDecision", () => {
  it("decodes a valid Respond JSON", () => {
    const out = decodeDecision('{"_tag":"Respond","content":"hello"}')
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "Respond") expect(out.value.content).toBe("hello")
  })

  it("decodes a valid CallCapability JSON (without callId)", () => {
    const out = decodeDecision(
      '{"_tag":"CallCapability","name":"read_file","arguments":{"path":"/ws"}}',
    )
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallCapability") {
      expect(out.value.name).toBe("read_file")
      expect(out.value.arguments).toEqual({ path: "/ws" })
    }
  })

  it("decodes a valid CallCapability JSON (with callId)", () => {
    const out = decodeDecision(
      '{"_tag":"CallCapability","name":"read_file","arguments":{"path":"/ws"},"callId":"t-1"}',
    )
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallCapability") {
      expect(out.value.name).toBe("read_file")
      expect(out.value.arguments).toEqual({ path: "/ws" })
      expect(out.value.callId).toBe("t-1")
    }
  })

  it("decodes a valid StartChildRun JSON (without grants)", () => {
    const out = decodeDecision(
      '{"_tag":"StartChildRun","role":"researcher","objective":"find docs"}',
    )
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "StartChildRun") {
      expect(out.value.role).toBe("researcher")
      expect(out.value.objective).toBe("find docs")
      expect(out.value.grants).toBeUndefined()
    }
  })

  it("decodes a valid StartChildRun JSON (with grants)", () => {
    const out = decodeDecision(
      '{"_tag":"StartChildRun","role":"researcher","objective":"find docs","grants":["g1","g2"]}',
    )
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "StartChildRun") {
      expect(out.value.grants).toEqual(["g1", "g2"])
    }
  })

  it("decodes a valid WaitForApproval JSON", () => {
    const out = decodeDecision('{"_tag":"WaitForApproval","question":"ok?"}')
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "WaitForApproval") expect(out.value.question).toBe("ok?")
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

  it("rejects legacy CallTool tag (D2.3 break clean — no compat)", () => {
    const out = decodeDecision('{"_tag":"CallTool","toolName":"read_file","args":{}}')
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
      '{"_tag":"CallCapability","name":"write_file","arguments":{"path":"a.txt","content":"hi"}}',
    ].join("\n")
    const out = decodeDecision(mixed)
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallCapability") {
      expect(out.value.name).toBe("write_file")
    }
  })

  it("decodes JSON wrapped in markdown code fence", () => {
    const fenced =
      "```json\n{\"_tag\":\"CallCapability\",\"name\":\"read_file\",\"arguments\":{}}\n```"
    const out = decodeDecision(fenced)
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallCapability") expect(out.value.name).toBe("read_file")
  })

  it("decodes JSON with trailing commas (LLM deviation)", () => {
    const trailing =
      '{"_tag":"CallCapability","name":"read_file","arguments":{"path":"/ws",},}'
    const out = decodeDecision(trailing)
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallCapability") {
      expect(out.value.name).toBe("read_file")
      expect((out.value.arguments as { path?: unknown }).path).toBe("/ws")
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
