/**
 * Project root map for the butler task layer.
 *
 * Kept separate from the route module so the runtime provider and the routes
 * share one parser without importing each other's handler bodies.
 */

/** BUTLER_V5_PROJECT_ROOTS='{"proj-1":"/srv/repos/proj-1"}' */
export function parseProjectRoots(env: NodeJS.ProcessEnv): Record<string, string> {
  const raw = (env["BUTLER_V5_PROJECT_ROOTS"] ?? "").trim()
  if (raw.length === 0) return {}
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    throw new Error("BUTLER_V5_PROJECT_ROOTS must be valid JSON")
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("BUTLER_V5_PROJECT_ROOTS must be an object of projectId -> root")
  }
  const roots: Record<string, string> = {}
  for (const [projectId, root] of Object.entries(parsed)) {
    if (typeof root !== "string" || root.length === 0) {
      throw new Error(`BUTLER_V5_PROJECT_ROOTS has an invalid root for ${projectId}`)
    }
    roots[projectId] = root
  }
  return roots
}
