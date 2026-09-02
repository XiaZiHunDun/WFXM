import { describe, expect, it } from "vitest"
import {
  matchGlobPath,
  parseProjectKnowledgeSourcesJson,
  resolveManifestSourceFiles,
} from "./project-knowledge-sources.js"
import { extensionOf, globPatternToRegExp, isMarkitdownExtension, isTextSnapshotExtension } from "./project-knowledge-sources.js"

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

  it("parses project with markitdownGlobs only", () => {
    const parsed = parseProjectKnowledgeSourcesJson(
      JSON.stringify({
        version: 1,
        projects: { WFXM: { globs: [], markitdownGlobs: ["docs/*.pdf"] } },
      }),
    )
    expect(parsed.ok).toBe(true)
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

describe("project knowledge source helper functions", () => {
  it("extracts lowercase extension, handling backslashes and dotfiles", () => {
    expect(extensionOf("docs/report.pdf")).toBe(".pdf")
    expect(extensionOf("C:\\docs\\file.DOCX")).toBe(".docx")
    expect(extensionOf("README")).toBe("")
    expect(extensionOf(".gitignore")).toBe("")
    expect(extensionOf("archive.tar.gz")).toBe(".gz")
  })

  it("marks office/doc extensions as markitdown-convertible", () => {
    expect(isMarkitdownExtension(".pdf")).toBe(true)
    expect(isMarkitdownExtension(".DOCX")).toBe(true)
    expect(isMarkitdownExtension(".xlsx")).toBe(true)
    expect(isMarkitdownExtension(".md")).toBe(false)
    expect(isMarkitdownExtension("")).toBe(false)
  })

  it("marks text/source extensions as text snapshots", () => {
    expect(isTextSnapshotExtension(".md")).toBe(true)
    expect(isTextSnapshotExtension(".markdown")).toBe(true)
    expect(isTextSnapshotExtension(".txt")).toBe(true)
    expect(isTextSnapshotExtension(".pdf")).toBe(false)
  })

  it("compiles glob patterns to anchored regex", () => {
    expect(globPatternToRegExp("*.md").test("notes.md")).toBe(true)
    expect(globPatternToRegExp("*.md").test("a/b.md")).toBe(false)
    expect(globPatternToRegExp("**/*.ts").test("a/b.ts")).toBe(true)
    expect(globPatternToRegExp("**/*.ts").test("b.ts")).toBe(true)
    expect(globPatternToRegExp("?.md").test("a.md")).toBe(true)
    expect(globPatternToRegExp("?.md").test("ab.md")).toBe(false)
    expect(globPatternToRegExp("docs\\*.txt").test("docs/readme.txt")).toBe(true)
  })
})
