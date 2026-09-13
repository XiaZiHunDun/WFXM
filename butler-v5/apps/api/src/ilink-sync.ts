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
  } catch (err) {
    // D61 T4 (audit #1 F-10): distinguish ENOENT (legitimate first-run,
    // silence is correct) from JSON parse error (corruption, must surface
    // for operators). Previously both returned "" and the poller treated
    // corruption the same as no state, silently resyncing from zero.
    const isMissing =
      err instanceof Error &&
      "code" in err &&
      (err as NodeJS.ErrnoException).code === "ENOENT"
    if (!isMissing) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error("[ilink-sync] loadSyncBuf parse error (file may be corrupt):", err)
    }
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
