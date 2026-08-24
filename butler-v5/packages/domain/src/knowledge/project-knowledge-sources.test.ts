import { describe, expect, it } from "vitest"
import {
  matchGlobPath,
  parseProjectKnowledgeSourcesJson,
  resolveManifestSourceFiles,
} from "./project-knowledge-sources.js"

describe("project-knowledge-sources", () => {
  it("parses a valid manifest", () => {
    const parsed = parseProjectKnowledgeSourcesJson(
      JSON.stringify({
        version: 1,
        projects: {
          WFXM: {
            globs: ["docs/**/*.md", "butler-v5/DESIGN.md"],
            markitdownGlobs: ["docs/**/*.pdf"],
          },
        },
      }),
    )
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(parsed.manifest.projects["WFXM"]?.globs).toHaveLength(2)
  })

  it("rejects globs with traversal", () => {
    const parsed = parseProjectKnowledgeSourcesJson(
      JSON.stringify({
        version: 1,
        projects: { WFXM: { globs: ["../secret.md"] } },
      }),
    )
    expect(parsed.ok).toBe(false)
  })

  it("matches glob paths", () => {
    expect(matchGlobPath("docs/plans/foo.md", "docs/**/*.md")).toBe(true)
    expect(matchGlobPath("docs/plans/foo.txt", "docs/**/*.md")).toBe(false)
    expect(matchGlobPath("butler-v5/DESIGN.md", "butler-v5/DESIGN.md")).toBe(true)
  })

  it("resolves manifest files via listFiles callback", () => {
    const parsed = parseProjectKnowledgeSourcesJson(
      JSON.stringify({
        version: 1,
        projects: { WFXM: { globs: ["docs/a.md", "docs/b.pdf"] } },
      }),
    )
    if (!parsed.ok) throw new Error(parsed.reason)
    const files = resolveManifestSourceFiles({
      manifest: parsed.manifest,
      listFiles: (glob) => {
        if (glob === "docs/a.md") return ["docs/a.md"]
        if (glob === "docs/b.pdf") return ["docs/b.pdf"]
        return []
      },
    })
    expect(files).toHaveLength(2)
    expect(files.find((f) => f.relativePath === "docs/b.pdf")?.viaMarkitdown).toBe(true)
  })
})
