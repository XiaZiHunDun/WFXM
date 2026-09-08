/**
 * Per-user session state snapshot, used by `wechat-session-digest.ts` to
 * render the "since you were last here" message on session open.
 *
 * Mirrors the file-JSON pattern of `wechat-active-project.ts` (single
 * record file keyed by `fromUserId`) but with atomic write (write to
 * `.tmp`, then rename) so a concurrent crash mid-write cannot corrupt the
 * file. Captures are written after every bot reply (B 方向 推 2).
 *
 * The file is local-only, per-host. Multi-process deployments would need a
 * shared store; not in scope here (cross-process consistency is a
 * D-series 撞点, not assumed).
 */
import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join } from "node:path"

const DEFAULT_STORE_PATH = join(homedir(), ".config", "butler-v5", "wechat-session-state.json")

export type SessionRunStatus = "success" | "fail" | "none"

export type SessionState = {
  readonly openTaskCount: number | null
  readonly candidateCount: number | null
  /** Status of the most recent background run (subagent or task). "none"
   *  means no background run has been observed for this user yet. */
  readonly lastRunStatus: SessionRunStatus
  /** Wall-clock ms epoch at which the last bot reply was sent. */
  readonly lastReplyAt: number
}

type SessionStateStore = Record<string, SessionState>

export function wechatSessionStatePath(env: NodeJS.ProcessEnv = process.env): string {
  const configured = (env["BUTLER_V5_WECHAT_SESSION_STATE"] ?? "").trim()
  return configured || DEFAULT_STORE_PATH
}

function isSessionRunStatus(value: unknown): value is SessionRunStatus {
  return value === "success" || value === "fail" || value === "none"
}

function readSessionStore(path: string): SessionStateStore {
  try {
    const raw = readFileSync(path, "utf8")
    const parsed: unknown = JSON.parse(raw)
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {}
    }
    const out: SessionStateStore = {}
    for (const [userId, raw] of Object.entries(parsed)) {
      if (typeof userId !== "string") continue
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue
      const r = raw as Record<string, unknown>
      const lastReplyAt = typeof r["lastReplyAt"] === "number" ? r["lastReplyAt"] : 0
      const openTaskCount =
        typeof r["openTaskCount"] === "number" ? r["openTaskCount"] : null
      const candidateCount =
        typeof r["candidateCount"] === "number" ? r["candidateCount"] : null
      const lastRunStatus: SessionRunStatus = isSessionRunStatus(r["lastRunStatus"])
        ? r["lastRunStatus"]
        : "none"
      out[userId] = { openTaskCount, candidateCount, lastRunStatus, lastReplyAt }
    }
    return out
  } catch {
    return {}
  }
}

function writeSessionStore(path: string, store: SessionStateStore): void {
  mkdirSync(dirname(path), { recursive: true })
  const tmp = `${path}.tmp`
  writeFileSync(tmp, `${JSON.stringify(store, null, 2)}\n`, "utf8")
  renameSync(tmp, path)
}

export function readWechatSessionState(
  userId: string,
  env: NodeJS.ProcessEnv = process.env,
): SessionState | null {
  const key = userId.trim()
  if (!key) return null
  const store = readSessionStore(wechatSessionStatePath(env))
  return store[key] ?? null
}

export function writeWechatSessionState(
  userId: string,
  state: SessionState,
  env: NodeJS.ProcessEnv = process.env,
): void {
  const key = userId.trim()
  if (!key) return
  const path = wechatSessionStatePath(env)
  const store = readSessionStore(path)
  store[key] = state
  writeSessionStore(path, store)
}
