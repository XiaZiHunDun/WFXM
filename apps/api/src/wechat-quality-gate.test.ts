import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { tryWechatQualityGateCommand } from "./wechat-quality-gate.js"

// D58 T5 (audit #3 F-06): the "未配置质量门禁" error reply used to embed
// the raw internal project id "wechat" — but the catalog shows the
// owner-facing label for that id is "WFXM". Owner UI elsewhere shows
// "WFXM" so the error reply must too.
describe("tryWechatQualityGateCommand (D58 T5 owner-facing label)", () => {
  it("uses owner-facing label 'WFXM' instead of raw id 'wechat' when no config", async () => {
    const dir = mkdtempSync(join(tmpdir(), "qg-test-"))
    const cfgPath = join(dir, "qg.json")
    // Empty projects map — gateProject returns undefined for 'wechat' and
    // we hit the missing-config branch.
    writeFileSync(cfgPath, JSON.stringify({ version: 1, projects: {} }))
    const result = await tryWechatQualityGateCommand({
      fromUserId: "owner-1",
      content: "/验",
      env: { BUTLER_V5_QUALITY_GATE_CONFIG: cfgPath },
    })
    expect(result).not.toBeNull()
    const reply = result?.reply ?? ""
    expect(reply).toContain("WFXM")
    expect(reply).not.toContain("项目「wechat」")
  })

  it("uses raw id when no catalog entry exists for the project id", async () => {
    // Defensive: a brand-new id that has no label fallback should still
    // surface the id (better than empty string). Documents the contract
    // for project ids that aren't in parseWechatProjectCatalog.
    const dir = mkdtempSync(join(tmpdir(), "qg-test-"))
    const cfgPath = join(dir, "qg.json")
    writeFileSync(cfgPath, JSON.stringify({ version: 1, projects: {} }))
    const result = await tryWechatQualityGateCommand({
      fromUserId: "owner-1",
      content: "/验",
      env: {
        BUTLER_V5_QUALITY_GATE_CONFIG: cfgPath,
        // Force an unknown id; BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE lets
        // us point the user at a project id without touching the catalog.
        BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(dir, "active.json"),
        BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "",
      },
    })
    expect(result).not.toBeNull()
    const reply = result?.reply ?? ""
    // Default active id when no store file is "wechat"; reply should now
    // contain the label "WFXM", not the raw id.
    expect(reply).toContain("WFXM")
  })
})

// Phase 6 T3: the repo flattened `butler-v5/` in Phase 1, but the checked-in
// config still pointed `wechat.cwd` at it, so `/验` could only ever spawn
// into a missing directory. Guard the real config against that rot.
describe("config/quality-gate.json", () => {
  it("every project cwd exists under the workspace root", () => {
    const cfgPath = resolve(process.cwd(), "config/quality-gate.json")
    const parsed = JSON.parse(readFileSync(cfgPath, "utf8")) as {
      projects?: Record<string, { cwd?: string }>
    }
    for (const [projectId, project] of Object.entries(parsed.projects ?? {})) {
      const rel = (project.cwd ?? ".").trim() || "."
      expect(existsSync(resolve(process.cwd(), rel)), `${projectId} -> ${rel}`).toBe(true)
    }
  })
})
