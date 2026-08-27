import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"
import { parseProjectKnowledgeSourcesJson } from "@butler/domain/knowledge/project-knowledge-sources.js"

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../..")

describe("project-knowledge-sources.json (production manifest)", () => {
  it("includes WFXM D1 and blackboard sources", () => {
    const text = readFileSync(join(repoRoot, "config/project-knowledge-sources.json"), "utf8")
    const parsed = parseProjectKnowledgeSourcesJson(text)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    const globs = parsed.manifest.projects["WFXM"]?.globs ?? []
    expect(globs).toContain("docs/plans/active/v5-d1-execution-handoff-2026-08-25.md")
    expect(globs).toContain("docs/plans/active/v5-architecture-alignment-handoff-2026-08.md")
    expect(globs).toContain("docs/plans/active/v5-p3-mcp-contract-issue-draft-2026-08.md")
    expect(globs).toContain(".blackboard/state.md")
    expect(globs).toContain("AGENTS.md")
    expect(globs.length).toBeGreaterThanOrEqual(20)
  })

  it("includes expanded LingWen novel-factory references", () => {
    const text = readFileSync(join(repoRoot, "config/project-knowledge-sources.json"), "utf8")
    const parsed = parseProjectKnowledgeSourcesJson(text)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    const globs = parsed.manifest.projects["LingWen"]?.globs ?? []
    expect(globs).toContain("projects/LingWen1/novel-factory/references/03-plot-timeline-foreshadowing.md")
    expect(globs).toContain("projects/LingWen1/novel-factory/references/06-locations-atlas-vol1.md")
    expect(globs).toContain("projects/LingWen1/novel-factory/references/09-character-relationships-timeline.md")
    expect(globs).toContain("projects/LingWen1/docs/pilot-setup.md")
    expect(globs.length).toBeGreaterThanOrEqual(20)
  })
})
