/**
 * P3 architecture seam guard (static):
 *
 * Acceptance: "Trigger 和 Capability 之外不存在第三条扩展接缝" and
 * "扩展不能创建第二套 Policy、状态机或数据源".
 *
 * These rules are kept intentionally narrow + robust (source scanning, no
 * dependency on the full TS graph). They fail the suite if a new entry point
 * bypasses the normalized RunTrigger seam, or an app starts reading/writing a
 * second persistence schema.
 */
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"
import { describe, expect, it } from "vitest"

function listTsFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    const stat = statSync(path)
    if (stat.isDirectory()) out.push(...listTsFiles(path))
    else if (entry.endsWith(".ts")) out.push(path)
  }
  return out
}

const SCAN_ROOTS = [
  join(process.cwd(), "apps"),
  join(process.cwd(), "cli"),
]

function productionFiles(): { file: string; src: string }[] {
  const out: { file: string; src: string }[] = []
  for (const root of SCAN_ROOTS) {
    for (const file of listTsFiles(root)) {
      const base = file.replace(/\\/g, "/")
      if (base.includes(".test.ts") || base.endsWith(".tsx")) continue
      out.push({ file: relative(process.cwd(), file), src: readFileSync(file, "utf8") })
    }
  }
  return out
}

const BUILD_OR_VALIDATE_TRIGGER = /\bbuild\w*RunTrigger\b|\bvalidateRunTrigger\b/

describe("P3 seam guard (architecture)", () => {
  it("no entry point starts a run outside the normalized RunTrigger seam", () => {
    const violations: string[] = []
    for (const { file, src } of productionFiles()) {
      const wasEntry = /\bexecuteInbound\s*\(/.test(src)
      // resumeRun is a resume of an already-validated external-approval run.
      const wasResume = /\bresumeRun\s*\(/.test(src)
      if (wasEntry && !BUILD_OR_VALIDATE_TRIGGER.test(src)) {
        violations.push(`${file}: executeInbound without build/validate RunTrigger`)
      }
      if (wasResume && !/\bRunTrigger\b/.test(src)) {
        violations.push(`${file}: resumeRun without a RunTrigger contract`)
      }
    }
    expect(violations).toEqual([])
  })

  it("no production source reads/writes a second persistence schema", () => {
    const violations: string[] = []
    for (const { file, src } of productionFiles()) {
      if (/from\s+["']@butler\/persistence\/schema/.test(src)) {
        violations.push(`${file}: direct @butler/persistence/schema import (second data source)`)
      }
    }
    expect(violations).toEqual([])
  })

  it("the engine chokepoint rejects an invalid RunTrigger (behavioral)", async () => {
    const { buildWechatRunTrigger, validateRunTrigger } = await import(
      "@butler/domain/runtime.js"
    )
    const valid = buildWechatRunTrigger({
      userId: "owner-1",
      conversationId: "c1",
      content: "hi",
      messageId: "m1",
    })
    expect(validateRunTrigger(valid).ok).toBe(true)
    expect(
      validateRunTrigger({ ...valid, idempotencyKey: "", source: "channel", conversationRef: "" })
        .ok,
    ).toBe(false)
  })
})