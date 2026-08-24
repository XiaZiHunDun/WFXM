/**
 * Expand declared globs to workspace-relative file paths (K1.1).
 */
import { existsSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"
import { matchGlobPath } from "@butler/domain/knowledge/project-knowledge-sources.js"

const DEFAULT_MAX_FILES = 200
const SKIP_DIR_NAMES = new Set(["node_modules", ".git", "dist"])

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
      if (SKIP_DIR_NAMES.has(entry.name)) continue
      walkFiles(root, abs, out, maxFiles)
      continue
    }
    if (entry.isFile()) {
      out.push(relative(root, abs).replace(/\\/g, "/"))
    }
  }
}

function listScopedDirectory(
  workspaceRoot: string,
  dirPart: string,
  pattern: string,
  maxFiles: number,
): readonly string[] {
  const absDir = join(workspaceRoot, dirPart)
  let entries: readonly { name: string; isFile: () => boolean }[]
  try {
    entries = readdirSync(absDir, { withFileTypes: true })
  } catch {
    return []
  }
  const matches: string[] = []
  for (const entry of entries) {
    if (!entry.isFile()) continue
    const rel = `${dirPart}/${entry.name}`.replace(/\\/g, "/")
    if (matchGlobPath(rel, pattern)) matches.push(rel)
    if (matches.length >= maxFiles) break
  }
  return matches
}

function walkFromPrefix(
  workspaceRoot: string,
  prefix: string,
  pattern: string,
  maxFiles: number,
): readonly string[] {
  const absPrefix = join(workspaceRoot, prefix)
  const collected: string[] = []
  walkFiles(workspaceRoot, absPrefix, collected, maxFiles * 8)
  return collected.filter((path) => matchGlobPath(path, pattern)).slice(0, maxFiles)
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

  const doubleStarIdx = pattern.indexOf("/**/")
  if (doubleStarIdx >= 0) {
    const prefix = pattern.slice(0, doubleStarIdx)
    if (prefix && !prefix.includes("*") && !prefix.includes("?")) {
      return walkFromPrefix(workspaceRoot, prefix, pattern, maxFiles)
    }
  }

  if (pattern.endsWith("/**")) {
    const prefix = pattern.slice(0, -3)
    if (prefix && !prefix.includes("*") && !prefix.includes("?")) {
      const collected: string[] = []
      walkFiles(workspaceRoot, join(workspaceRoot, prefix), collected, maxFiles * 8)
      return collected.slice(0, maxFiles)
    }
  }

  const slashIdx = pattern.lastIndexOf("/")
  if (slashIdx >= 0 && !pattern.includes("**")) {
    const dirPart = pattern.slice(0, slashIdx)
    const filePart = pattern.slice(slashIdx + 1)
    if (
      dirPart &&
      filePart &&
      !dirPart.includes("*") &&
      !dirPart.includes("?") &&
      !filePart.includes("/")
    ) {
      return listScopedDirectory(workspaceRoot, dirPart, pattern, maxFiles)
    }
  }

  const all: string[] = []
  walkFiles(workspaceRoot, workspaceRoot, all, maxFiles * 8)
  return all.filter((path) => matchGlobPath(path, pattern)).slice(0, maxFiles)
}
