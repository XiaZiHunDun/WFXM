import { readFileSync, existsSync } from "node:fs"
import { join } from "node:path"
import { Effect } from "effect"
import type { LLMAdapter, LLMAssistantResponse, LLMMessage, LLMTool } from "./llm-provider.js"

type FixtureEntry = {
  readonly content?: string
  readonly toolCalls?: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[]
  readonly stopReason?: LLMAssistantResponse["stopReason"]
}

type FixtureFile = {
  readonly responses?: readonly FixtureEntry[]
}

const counters = new Map<string, number>()

function fixtureKey(dir: string, role: string): string {
  return `${dir}::${role}`
}

/** Reset per-role call counters (tests only). */
export function resetFixtureLLMCounters(): void {
  counters.clear()
}

export function fixtureLLMPath(fixtureDir: string, role: string): string {
  return join(fixtureDir, `${role}.json`)
}

export function makeFixtureLLMAdapter(args: {
  readonly fixtureDir: string
  readonly role: string
}): LLMAdapter {
  const path = fixtureLLMPath(args.fixtureDir, args.role)
  let responses: readonly FixtureEntry[] = []
  if (existsSync(path)) {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as FixtureFile
    responses = parsed.responses ?? []
  }
  const key = fixtureKey(args.fixtureDir, args.role)
  return {
    complete: (_messages: readonly LLMMessage[], _opts?: { readonly tools?: readonly LLMTool[] }) => {
      const index = counters.get(key) ?? 0
      counters.set(key, index + 1)
      const entry = responses[index] ?? {
        content: `[fixture exhausted: ${args.role}#${index}]`,
        toolCalls: [],
        stopReason: "end_turn" as const,
      }
      return Effect.succeed({
        content: entry.content ?? "",
        toolCalls: entry.toolCalls ?? [],
        stopReason: entry.stopReason ?? "end_turn",
      })
    },
  }
}

export function pickLLMFixtureDir(env: NodeJS.ProcessEnv = process.env): string | undefined {
  const raw = (env["BUTLER_V5_LLM_FIXTURE_DIR"] ?? "").trim()
  return raw || undefined
}
