import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"

const OWNER_ROUTES_ENTRY = join(__dirname, "../../apps/api/src/owner-routes.ts")
const OWNER_ROUTES_DIR = join(__dirname, "../../apps/api/src/owner-routes")

/**
 * Owner control-surface route source = aggregation entry + all submodule files.
 * owner-routes.ts was split into ./owner-routes/*.ts (file-size gate); arch
 * guards must scan the whole surface, not just the aggregation entry.
 */
export function readOwnerRoutesSource(): string {
  const parts = [readFileSync(OWNER_ROUTES_ENTRY, "utf-8")]
  for (const name of readdirSync(OWNER_ROUTES_DIR).sort()) {
    if (name.endsWith(".ts")) {
      parts.push(readFileSync(join(OWNER_ROUTES_DIR, name), "utf-8"))
    }
  }
  return parts.join("\n")
}
