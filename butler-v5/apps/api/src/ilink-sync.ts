import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { dirname } from "node:path"

export function loadSyncBuf(path: string): string {
  try {
    const raw = readFileSync(path, "utf8")
    const parsed: unknown = JSON.parse(raw)
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return ""
    }
    const buf = (parsed as Record<string, unknown>)["get_updates_buf"]
    return typeof buf === "string" ? buf : ""
  } catch {
    return ""
  }
}

export function saveSyncBuf(path: string, syncBuf: string): void {
  try {
    mkdirSync(dirname(path), { recursive: true })
    writeFileSync(path, `${JSON.stringify({ get_updates_buf: syncBuf })}\n`, {
      encoding: "utf8",
      mode: 0o600,
    })
  } catch {
    // Persistence is best-effort; the poller must keep running.
  }
}
