// Anchors: apps are driving adapters only — no infrastructure imports, no
// direct upstream LLM calls, no second loop/policy, and every LLM entry point
// funnels through the canonical runButlerLoop. Merged from the former
// §1.1/§3 #2/#3/#6 and §20 #4 guards.
import { describe, expect, it } from "vitest"
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"

const APPS = join(process.cwd(), "apps")
const API_SRC = join(APPS, "api/src")

function listTsFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "dist") continue
    const path = join(dir, entry)
    const stat = statSync(path)
    if (stat.isDirectory()) out.push(...listTsFiles(path))
    else if (entry.endsWith(".ts")) out.push(path)
  }
  return out
}

function productionFiles(): string[] {
  return listTsFiles(APPS).filter((f) => !f.endsWith(".test.ts"))
}

function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "")
}

describe("apps layer boundaries", () => {
  it("apps production sources do not import infrastructure/application layers", () => {
    const violations: string[] = []
    for (const file of productionFiles()) {
      const src = readFileSync(file, "utf8")
      for (const banned of ["@butler/infrastructure", "@butler/application"]) {
        if (src.includes(banned)) violations.push(`${relative(process.cwd(), file)}: ${banned}`)
      }
    }
    expect(violations).toEqual([])
  })

  it("wechat intake stays parsing/normalization only (no policy/decision logic)", () => {
    const src = readFileSync(join(API_SRC, "wechat-intake.ts"), "utf8")
    const forbidden = [
      /\bPolicyGate\b/,
      /\bCapabilityRegistry\b/,
      /\bdecidePermission\b/,
      /\bdecidePolicy\b/,
      /\bActiveMainRunConflict\b/,
      /\bgrantMatchesAction\b/,
    ]
    const hits = forbidden.filter((re) => re.test(src)).map((re) => re.source)
    expect(hits).toEqual([])
  })

  it("apps do not fetch upstream LLM endpoints directly", () => {
    const forbidden = [
      /fetch\(\s*["'`][^"'`]*anthropic\.com/,
      /fetch\(\s*["'`][^"'`]*openai\.com/,
      /fetch\(\s*["'`][^"'`]*deepseek\.com/,
      /fetch\(\s*["'`][^"'`]*dashscope\.aliyuncs\.com/,
    ]
    const violations: string[] = []
    for (const file of productionFiles()) {
      const src = stripComments(readFileSync(file, "utf8"))
      for (const re of forbidden) {
        if (re.test(src)) violations.push(`${relative(process.cwd(), file)}: ${re.source}`)
      }
    }
    expect(violations).toEqual([])
  })

  it("apps do not define a second LLM loop / policy gate / engine", () => {
    const forbidden = [
      /^(?:export\s+)?class\s+\w*(?:Loop|LoopEngine|ConversationEngine|Orchestrator)\b/m,
      /^(?:export\s+)?class\s+\w*PolicyGate\b/m,
      /^(?:export\s+)?class\s+\w*Engine\b/m,
    ]
    const violations: string[] = []
    for (const file of productionFiles()) {
      const src = readFileSync(file, "utf8")
      for (const re of forbidden) {
        if (re.test(src)) violations.push(`${relative(process.cwd(), file)}: ${re.source}`)
      }
    }
    expect(violations).toEqual([])
  })

  it("every LLM entry point reaches the canonical loop via runButlerLoop", () => {
    const entryPoints = [
      "cli-run.ts",
      "task-run.ts",
      "schedule-run.ts",
      "wechat-intake.ts",
      "channel-inbound.ts",
      "routes/inbound.ts",
    ]
    for (const name of entryPoints) {
      const path = join(API_SRC, name)
      if (!existsSync(path)) continue
      expect(readFileSync(path, "utf8"), `${name} must import runButlerLoop`).toMatch(
        /import\s*\{[^}]*runButlerLoop[^}]*\}\s*from\s*["']\.{1,2}\/wechat-inbound-butler\.js["']/,
      )
    }
    // Health probe is deliberately outside the LLM path.
    const health = join(API_SRC, "routes/health.ts")
    if (existsSync(health)) {
      expect(readFileSync(health, "utf8")).not.toContain("runButlerLoop")
    }
  })
})
