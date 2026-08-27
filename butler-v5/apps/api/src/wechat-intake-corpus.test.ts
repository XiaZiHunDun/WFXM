import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { classifyWechatIntentWithLlm } from "./wechat-intake-llm.js"
import { classifyWechatIntent, resolveIntakeLoopOptions } from "./wechat-intake.js"
import { toolSurfaceMatchesCorpus } from "./wechat-tool-profile.js"

type CorpusCase = {
  readonly id: string
  readonly utterance: string
  readonly expect: {
    readonly intent: string
    readonly locked: boolean
    readonly toolSurface: string
    readonly execVia: string
  }
}

type CorpusFile = {
  readonly cases: readonly CorpusCase[]
}

function loadCorpus(): CorpusFile {
  const path = join(process.cwd(), "config/wechat-intake-corpus.json")
  return JSON.parse(readFileSync(path, "utf8")) as CorpusFile
}

const subagentEnv = {
  BUTLER_V5_SUBAGENT_ENABLED: "1",
  BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: "",
  BUTLER_V5_DEV_DIRECT_EXEC: "0",
}

describe("wechat-intake-corpus (T1)", () => {
  const corpus = loadCorpus()

  it.each(corpus.cases.map((c) => [c.id, c] as const))(
    "rules classify %s",
    (_id, item) => {
      const intent = classifyWechatIntent(item.utterance)
      expect(intent.kind).toBe(item.expect.intent)
    },
  )

  it.each(
    corpus.cases
      .filter((c) => c.expect.toolSurface !== "plan" || c.expect.intent === "chat")
      .map((c) => [c.id, c] as const),
  )("tool surface %s", (_id, item) => {
    const intent = classifyWechatIntent(item.utterance)
    const opts = resolveIntakeLoopOptions({
      intent,
      projectId: "wechat",
      env: subagentEnv,
    })
    expect(
      toolSurfaceMatchesCorpus({
        intentKind: intent.kind,
        allowedToolNames: opts.allowedToolNames,
        expectToolSurface: item.expect.toolSurface,
        env: subagentEnv,
      }),
    ).toBe(true)
    if (item.expect.execVia === "child_run") {
      expect(opts.allowedToolNames).toContain("delegate_to_subagent")
      expect(opts.allowedToolNames).not.toContain("write_file")
      expect(opts.allowedToolNames).not.toContain("run_command")
      expect(opts.includeExecTools).toBe(false)
      expect(opts.requiresDevSession).toBe(true)
    }
    if (item.expect.execVia === "none" && item.expect.intent === "chat") {
      expect(opts.includeExecTools).toBe(false)
    }
  })

  it.each(corpus.cases.filter((c) => c.expect.locked).map((c) => [c.id, c] as const))(
    "locked %s survives LLM downgrade attempt",
    async (_id, item) => {
      const fallback = classifyWechatIntent(item.utterance)
      const out = await classifyWechatIntentWithLlm({
        content: item.utterance,
        fallback,
        env: { ...subagentEnv, BUTLER_V5_INTAKE_LLM: "1", DEEPSEEK_API_KEY: "sk-fake" },
      })
      expect(out.source).toBe("rules")
      expect(out.intent.kind).toBe(item.expect.intent)
    },
  )
})

describe("scheme B defaults", () => {
  it("dev_task uses delegate not direct exec", () => {
    const opts = resolveIntakeLoopOptions({
      intent: { kind: "dev_task", goal: "fix bug" },
      projectId: "wechat",
      env: subagentEnv,
    })
    expect(opts.allowedToolNames).toContain("delegate_to_subagent")
    expect(opts.allowedToolNames).not.toContain("write_file")
    expect(opts.includeExecTools).toBe(false)
  })

  it("legacy direct exec opt-in", () => {
    const opts = resolveIntakeLoopOptions({
      intent: { kind: "dev_task", goal: "fix bug" },
      projectId: "wechat",
      env: { ...subagentEnv, BUTLER_V5_DEV_DIRECT_EXEC: "1" },
    })
    expect(opts.allowedToolNames).toContain("write_file")
    expect(opts.allowedToolNames).not.toContain("delegate_to_subagent")
    expect(opts.includeExecTools).toBe(true)
  })
})
