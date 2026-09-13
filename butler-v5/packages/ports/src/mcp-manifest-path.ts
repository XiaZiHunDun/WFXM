/**
 * D61 T5 (audit #2 F-10 domain purity): moved from
 * `packages/domain/src/mcp/manifest.ts` to ports because it imports
 * `node:path` (`dirname`, `isAbsolute`, `resolve`). Domain must remain
 * pure (no node built-ins); ports is the appropriate layer for path
 * resolution utilities.
 *
 * Re-exported from `@butler/domain/mcp/manifest` for backward compatibility
 * with existing call sites (apps/api/src/mcp-config.ts).
 */
import { dirname, isAbsolute, resolve } from "node:path"

export function resolveManifestStdioArgs(
  manifestPath: string,
  args: readonly string[],
): readonly string[] {
  if (args.length === 0) return args
  const baseDir = dirname(resolve(manifestPath))
  const out: string[] = []
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    if (arg === undefined) continue
    if (arg === "--openapi-spec") {
      const specPath = args[i + 1]
      if (specPath !== undefined) {
        out.push(arg)
        out.push(isAbsolute(specPath) ? specPath : resolve(baseDir, specPath))
        i++
        continue
      }
    }
    out.push(arg)
  }
  return out
}
