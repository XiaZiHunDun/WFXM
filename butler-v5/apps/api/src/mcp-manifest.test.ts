import { mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import {
  assertMcpServerInManifest,
  loadMcpManifestFromPath,
  mcpManifestPathFromEnv,
} from "./mcp-manifest.js"

describe("MCP manifest loader", () => {
  it("returns none when env path is unset", () => {
    expect(mcpManifestPathFromEnv({})).toBeNull()
  })

  it("loads manifest json from disk", () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-mcp-manifest-"))
    const path = join(dir, "mcp.json")
    writeFileSync(
      path,
      JSON.stringify({
        version: 1,
        servers: [{ id: "tools.example.com", transport: "http", url: "http://127.0.0.1/mcp" }],
      }),
    )
    const loaded = loadMcpManifestFromPath(path)
    expect(loaded.kind).toBe("loaded")
    if (loaded.kind !== "loaded") return
    expect(assertMcpServerInManifest(loaded.manifest, "tools.example.com")).toEqual({ ok: true })
  })

  it("reports missing files", () => {
    const loaded = loadMcpManifestFromPath("/tmp/does-not-exist-butler-mcp-manifest.json")
    expect(loaded.kind).toBe("error")
  })
})
