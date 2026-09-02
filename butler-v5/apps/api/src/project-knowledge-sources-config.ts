/**
 * Load project-knowledge-sources.json (K1.1).
 */
import { readFileSync } from "node:fs"
import { envTruthy } from "./env-util.js"
import { resolve } from "node:path"
import {
  parseProjectKnowledgeSourcesJson,
  type ProjectKnowledgeSourcesManifest,
} from "@butler/domain/knowledge/project-knowledge-sources.js"

export type ProjectKnowledgeSourcesLoadResult =
  | { readonly kind: "none" }
  | { readonly kind: "loaded"; readonly manifest: ProjectKnowledgeSourcesManifest }
  | { readonly kind: "error"; readonly reason: string }

export function projectKnowledgeSourcesPathFromEnv(
  env: NodeJS.ProcessEnv = process.env,
): string | null {
  const raw = (env["BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH"] ?? "").trim()
  if (raw) return raw
  return "config/project-knowledge-sources.json"
}

export function loadProjectKnowledgeSourcesFromPath(
  path: string,
): ProjectKnowledgeSourcesLoadResult {
  try {
    const abs = resolve(path)
    const raw = readFileSync(abs, "utf8")
    const parsed = parseProjectKnowledgeSourcesJson(raw)
    if (!parsed.ok) {
      return { kind: "error", reason: parsed.reason }
    }
    return { kind: "loaded", manifest: parsed.manifest }
  } catch (err) {
    return {
      kind: "error",
      reason: err instanceof Error ? err.message : String(err),
    }
  }
}

export function loadProjectKnowledgeSourcesFromEnv(
  env: NodeJS.ProcessEnv = process.env,
  cwd: string = process.cwd(),
): ProjectKnowledgeSourcesLoadResult {
  const path = projectKnowledgeSourcesPathFromEnv(env)
  if (!path) return { kind: "none" }
  return loadProjectKnowledgeSourcesFromPath(resolve(cwd, path))
}


export interface ProjectKnowledgeWatchConfig {
  readonly enabled: boolean
  readonly tickMs: number
  readonly sourcesPath: string | null
}

export function parseProjectKnowledgeWatchConfig(
  env: NodeJS.ProcessEnv = process.env,
): ProjectKnowledgeWatchConfig {
  const enabled = envTruthy(env["BUTLER_V5_PROJECT_KNOWLEDGE_WATCH"])
  const tickMsRaw = Number(env["BUTLER_V5_PROJECT_KNOWLEDGE_WATCH_MS"] ?? 300_000)
  const tickMs = Number.isFinite(tickMsRaw) && tickMsRaw > 0 ? Math.floor(tickMsRaw) : 300_000
  return {
    enabled,
    tickMs,
    sourcesPath: projectKnowledgeSourcesPathFromEnv(env),
  }
}

export function isProjectKnowledgeWatchEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_PROJECT_KNOWLEDGE_WATCH"])
}
