/**
 * Project Knowledge sources manifest (K1.1).
 * Declares per-project workspace globs allowed for watch/sync ingest.
 */

export interface ProjectKnowledgeSourcesProject {
  readonly globs: readonly string[]
  /** Optional extra globs ingested via markitdown MCP → document → promote. */
  readonly markitdownGlobs?: readonly string[]
}

export interface ProjectKnowledgeSourcesManifest {
  readonly version: number
  readonly projects: Readonly<Record<string, ProjectKnowledgeSourcesProject>>
}

export type ProjectKnowledgeSourcesParseResult =
  | { readonly ok: true; readonly manifest: ProjectKnowledgeSourcesManifest }
  | { readonly ok: false; readonly reason: string }

const DEFAULT_MARKITDOWN_EXTENSIONS = new Set([
  ".pdf",
  ".docx",
  ".doc",
  ".pptx",
  ".ppt",
  ".xlsx",
  ".xls",
])

const DEFAULT_TEXT_EXTENSIONS = new Set([
  ".md",
  ".markdown",
  ".txt",
  ".json",
  ".yaml",
  ".yml",
  ".sql",
  ".ts",
  ".tsx",
  ".js",
  ".mjs",
  ".cjs",
  ".py",
  ".sh",
  ".toml",
  ".xml",
  ".html",
  ".css",
])

function normalizeGlob(raw: string): string | null {
  const g = raw.trim().replace(/\\/g, "/")
  if (!g || g.includes("..")) return null
  return g
}

function parseProjectEntry(raw: unknown): ProjectKnowledgeSourcesProject | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null
  const obj = raw as Record<string, unknown>
  const globsRaw = obj["globs"]
  if (!Array.isArray(globsRaw)) return null
  const globs: string[] = []
  for (const item of globsRaw) {
    if (typeof item !== "string") continue
    const g = normalizeGlob(item)
    if (g) globs.push(g)
  }
  const markitdownGlobs: string[] = []
  const mdRaw = obj["markitdownGlobs"]
  if (Array.isArray(mdRaw)) {
    for (const item of mdRaw) {
      if (typeof item !== "string") continue
      const g = normalizeGlob(item)
      if (g) markitdownGlobs.push(g)
    }
  }
  if (globs.length === 0 && markitdownGlobs.length === 0) return null
  return {
    globs,
    ...(markitdownGlobs.length > 0 ? { markitdownGlobs } : {}),
  }
}

export function parseProjectKnowledgeSourcesJson(text: string): ProjectKnowledgeSourcesParseResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { ok: false, reason: "invalid JSON" }
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, reason: "manifest must be an object" }
  }
  const root = parsed as Record<string, unknown>
  const version = typeof root["version"] === "number" ? root["version"] : 1
  const projectsRaw = root["projects"]
  if (!projectsRaw || typeof projectsRaw !== "object" || Array.isArray(projectsRaw)) {
    return { ok: false, reason: "projects must be an object" }
  }
  const projects: Record<string, ProjectKnowledgeSourcesProject> = {}
  for (const [projectId, entry] of Object.entries(projectsRaw as Record<string, unknown>)) {
    const id = projectId.trim()
    if (!id) continue
    const project = parseProjectEntry(entry)
    if (project) projects[id] = project
  }
  if (Object.keys(projects).length === 0) {
    return { ok: false, reason: "no valid projects in manifest" }
  }
  return { ok: true, manifest: { version, projects } }
}

/** Convert a simple glob (`*`, `**`, `?`) to a RegExp for POSIX-style paths. */
export function globPatternToRegExp(pattern: string): RegExp {
  const normalized = pattern.replace(/\\/g, "/")
  let re = "^"
  for (let i = 0; i < normalized.length; i += 1) {
    const ch = normalized[i] ?? ""
    if (ch === "*") {
      const next = normalized[i + 1]
      if (next === "*") {
        re += ".*"
        i += 1
        if (normalized[i + 1] === "/") i += 1
      } else {
        re += "[^/]*"
      }
      continue
    }
    if (ch === "?") {
      re += "[^/]"
      continue
    }
    if ("\\^$+.|()[]{}".includes(ch)) {
      re += `\\${ch}`
    } else {
      re += ch
    }
  }
  re += "$"
  return new RegExp(re)
}

export function matchGlobPath(relativePath: string, pattern: string): boolean {
  const path = relativePath.replace(/\\/g, "/")
  const pat = pattern.replace(/\\/g, "/")
  return globPatternToRegExp(pat).test(path)
}

export function extensionOf(relativePath: string): string {
  const base = relativePath.replace(/\\/g, "/").split("/").pop() ?? relativePath
  const idx = base.lastIndexOf(".")
  if (idx <= 0) return ""
  return base.slice(idx).toLowerCase()
}

export function isMarkitdownExtension(ext: string): boolean {
  return DEFAULT_MARKITDOWN_EXTENSIONS.has(ext.toLowerCase())
}

export function isTextSnapshotExtension(ext: string): boolean {
  return DEFAULT_TEXT_EXTENSIONS.has(ext.toLowerCase())
}

export interface ResolvedSourceFile {
  readonly projectId: string
  readonly relativePath: string
  readonly viaMarkitdown: boolean
}

export function resolveManifestSourceFiles(input: {
  readonly manifest: ProjectKnowledgeSourcesManifest
  readonly listFiles: (glob: string) => readonly string[]
}): readonly ResolvedSourceFile[] {
  const seen = new Set<string>()
  const out: ResolvedSourceFile[] = []
  for (const [projectId, project] of Object.entries(input.manifest.projects)) {
    const allPatterns = [
      ...project.globs.map((g) => ({ glob: g, viaMarkitdown: false as const })),
      ...(project.markitdownGlobs ?? []).map((g) => ({ glob: g, viaMarkitdown: true as const })),
    ]
    for (const { glob, viaMarkitdown } of allPatterns) {
      for (const relativePath of input.listFiles(glob)) {
        const key = `${projectId}\0${relativePath}`
        if (seen.has(key)) continue
        seen.add(key)
        const ext = extensionOf(relativePath)
        const useMarkitdown =
          viaMarkitdown || (isMarkitdownExtension(ext) && !isTextSnapshotExtension(ext))
        out.push({ projectId, relativePath, viaMarkitdown: useMarkitdown })
      }
    }
  }
  return out
}
