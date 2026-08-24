/**
 * Expand declared globs to workspace-relative file paths (K1.1).
 */
import { existsSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"
import { matchGlobPath } from "@butler/domain/knowledge/project-knowledge-sources.js"

const DEFAULT_MAX_FILES = 200

function isPlainPath(glob: string): boolean {
  return !glob.includes("*") && !glob.includes("?")
}

function walkFiles(root: string, dir: string, out: string[], maxFiles: number): void {
  if (out.length >= maxFiles) return
  let entries: readonly { name: string; isDirectory: () => boolean; isFile: () => boolean }[]
  try {
    entries = readdirSync(dir, { withFileTypes: true })
  } catch {
    return
  }
  for (const entry of entries) {
    if (out.length >= maxFiles) return
    const abs = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".git" || entry.name === "dist") continue
      walkFiles(root, abs, out, maxFiles)
      continue
    }
    if (entry.isFile()) {
      out.push(relative(root, abs).replace(/\\/g, "/"))
    }
  }
}

export function listWorkspaceFilesForGlob(
  workspaceRoot: string,
  glob: string,
  maxFiles: number = DEFAULT_MAX_FILES,
): readonly string[] {
  const pattern = glob.trim().replace(/\\/g, "/")
  if (!pattern || pattern.includes("..")) return []

  if (isPlainPath(pattern)) {
    const abs = join(workspaceRoot, pattern)
    try {
      if (existsSync(abs) && statSync(abs).isFile()) return [pattern]
    } catch {
      return []
    }
    return []
  }

  const all: string[] = []
  walkFiles(workspaceRoot, workspaceRoot, all, maxFiles * 4)
  return all.filter((path) => matchGlobPath(path, pattern)).slice(0, maxFiles)
}
