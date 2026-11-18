import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { buildWechatInboundMessages, stubReply } from "./wechat-inbound-llm.js"

// D82 T3: the three generateLLMReply cases were removed with the function —
// it was dead, and its "LLM call fails" cases made real outbound requests to
// api.anthropic.com / api.deepseek.com with fake keys, so they were also the
// only network-dependent tests in apps/api (source of an intermittent full-run
// failure observed during D82 T1/T2 verification).

const ORIGINAL_ENV = { ...process.env }

describe("wechat-inbound-llm", () => {
  beforeEach(() => {
    for (const k of Object.keys(process.env)) delete process.env[k]
    Object.assign(process.env, ORIGINAL_ENV)
  })

  afterEach(() => {
    for (const k of Object.keys(process.env)) delete process.env[k]
    Object.assign(process.env, ORIGINAL_ENV)
    vi.restoreAllMocks()
  })

  it("buildWechatInboundMessages returns system + user tuple", () => {
    const msgs = buildWechatInboundMessages("hello")
    expect(msgs).toHaveLength(2)
    expect(msgs[0]?.role).toBe("system")
    expect(msgs[1]?.role).toBe("user")
    expect(msgs[1]?.content).toBe("hello")
  })

  // D60 T2.1 (audit #3 F-02): owner-facing reply must omit raw fromUserId +
  // raw projectId + 'MVP stub reply' jargon (3x D48 §4 violation).
  it("stubReply omits fromUserId, projectId, and MVP jargon", () => {
    const reply = stubReply("hi", "u-1", "proj-1")
    expect(reply).not.toContain("u-1")
    expect(reply).not.toContain("proj-1")
    expect(reply).not.toMatch(/MVP stub/)
    expect(reply).not.toMatch(/v5 received/)
    // Owner still gets confirmation the message was received.
    expect(reply).toContain("已收到")
  })

  // D82 T3: the prompt declared its shapes with tag `CallCapability` /
  // `StartChildRun` but its closing prose told the model to "use CallTool" /
  // "use Delegate". Neither is a real tag, so the model had to guess the
  // mapping; a real LLM guessed literally and emitted `{"_tag":"Delegate"}`,
  // which decodeDecision rejected (the D81 decode bug). These pin both halves
  // of the contract so the prose cannot drift away from the declared shapes.
  describe("decision-tag vocabulary", () => {
    // advertiseDelegate = !includeExecTools && BUTLER_V5_SUBAGENT_ENABLED
    // (shouldAdvertiseDelegate in wechat-tool-profile.ts), so the prompt has
    // three shapes. Cover all three: each one used to name a pseudo-tag.
    const WITH_DELEGATE: NodeJS.ProcessEnv = { BUTLER_V5_SUBAGENT_ENABLED: "1" }
    const PROMPT_SHAPES = [
      { name: "delegate advertised", env: WITH_DELEGATE, opts: { includeExecTools: false } },
      { name: "exec tools, no delegate", env: {}, opts: { includeExecTools: true } },
      { name: "read-only, no delegate", env: {}, opts: { includeExecTools: false } },
    ] as const

    const systemPrompt = (
      env: NodeJS.ProcessEnv,
      opts: { readonly includeExecTools: boolean },
    ): string => buildWechatInboundMessages("hello", env, opts)[0]?.content ?? ""

    it("names only real tags, never the old CallTool/Delegate pseudo-tags", () => {
      for (const shape of PROMPT_SHAPES) {
        const prompt = systemPrompt(shape.env, shape.opts)
        expect(prompt, `shape: ${shape.name}`).not.toMatch(/\bCallTool\b/)
        expect(prompt, `shape: ${shape.name}`).not.toMatch(/\buse Delegate\b/)
        expect(prompt, `shape: ${shape.name}`).not.toMatch(/Prefer Delegate\b/)
      }
    })

    it("uses CallCapability and StartChildRun where the old pseudo-tags were", () => {
      // The delegate-advertised closing used to say "use Delegate ... instead
      // of CallTool"; the exec closing used to say "use CallTool directly".
      const delegate = systemPrompt(WITH_DELEGATE, { includeExecTools: false })
      expect(delegate).toContain("StartChildRun")
      expect(delegate).toContain("CallCapability")

      const exec = systemPrompt({}, { includeExecTools: true })
      expect(exec).toContain("CallCapability")
    })

    it("advertises StartChildRun only when delegate is actually available", () => {
      expect(systemPrompt(WITH_DELEGATE, { includeExecTools: false })).toContain(
        '"_tag":"StartChildRun"',
      )
      // includeExecTools hides delegate regardless of the env flag.
      expect(systemPrompt(WITH_DELEGATE, { includeExecTools: true })).not.toContain(
        '"_tag":"StartChildRun"',
      )
      // subagent disabled hides it too.
      expect(systemPrompt({}, { includeExecTools: false })).not.toContain('"_tag":"StartChildRun"')
    })

    it("declares only real tags, so no shape can reference an undeclared one", () => {
      for (const shape of PROMPT_SHAPES) {
        const prompt = systemPrompt(shape.env, shape.opts)
        const declared = [...prompt.matchAll(/"_tag":"(\w+)"/g)].map((m) => m[1])
        expect(declared.length, `shape: ${shape.name}`).toBeGreaterThan(0)
        for (const tag of declared) {
          expect(
            ["Respond", "CallCapability", "StartChildRun", "Finish", "WaitForApproval"],
            `shape ${shape.name} declared unknown tag ${tag}`,
          ).toContain(tag)
        }
      }
    })
  })
})
