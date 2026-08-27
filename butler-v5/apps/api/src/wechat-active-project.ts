import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join } from "node:path"

const DEFAULT_STORE_PATH = join(homedir(), ".config", "butler-v5", "wechat-active-project.json")

type ActiveProjectStore = Record<string, string>

const PROJECT_ALIASES: Readonly<Record<string, string>> = {
  wfxm: "wechat",
  WFXM: "wechat",
  lingwen: "LingWen1",
  LingWen: "LingWen1",
  灵文: "灵文1号",
}

export function wechatActiveProjectStorePath(env: NodeJS.ProcessEnv = process.env): string {
  const configured = (env["BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE"] ?? "").trim()
  return configured || DEFAULT_STORE_PATH
}

function readStore(path: string): ActiveProjectStore {
  try {
    const raw = readFileSync(path, "utf8")
    const parsed: unknown = JSON.parse(raw)
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {}
    }
    const out: ActiveProjectStore = {}
    for (const [userId, projectId] of Object.entries(parsed)) {
      if (typeof userId === "string" && typeof projectId === "string" && projectId.trim()) {
        out[userId.trim()] = projectId.trim()
      }
    }
    return out
  } catch {
    return {}
  }
}

function writeStore(path: string, store: ActiveProjectStore): void {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, `${JSON.stringify(store, null, 2)}\n`, "utf8")
}

export function parseWechatProjectCatalog(
  env: NodeJS.ProcessEnv = process.env,
): readonly { readonly id: string; readonly label: string }[] {
  const mapRaw = (
    env["BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP"] ?? "wechat:WFXM"
  ).trim()
  const seen = new Set<string>()
  const items: { id: string; label: string }[] = []
  const add = (id: string, label?: string) => {
    const normalized = id.trim()
    if (!normalized || seen.has(normalized)) return
    seen.add(normalized)
    items.push({ id: normalized, label: label ?? normalized })
  }
  add("wechat", "WFXM")
  if (!mapRaw) return items
  for (const pair of mapRaw.split(",")) {
    const colon = pair.indexOf(":")
    if (colon <= 0) continue
    const inboundId = pair.slice(0, colon).trim()
    const pkId = pair.slice(colon + 1).trim()
    if (inboundId) add(inboundId, pkId || inboundId)
  }
  return items
}

export function getWechatActiveProjectId(
  userId: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  const key = userId.trim()
  if (!key) return "wechat"
  const store = readStore(wechatActiveProjectStorePath(env))
  return store[key] ?? "wechat"
}

export function setWechatActiveProjectId(
  userId: string,
  projectId: string,
  env: NodeJS.ProcessEnv = process.env,
): void {
  const key = userId.trim()
  const value = projectId.trim()
  if (!key || !value) return
  const path = wechatActiveProjectStorePath(env)
  const store = readStore(path)
  store[key] = value
  writeStore(path, store)
}

export function resolveWechatProjectAlias(
  rawName: string,
  env: NodeJS.ProcessEnv = process.env,
): string | null {
  const name = rawName.trim()
  if (!name) return null
  const alias = PROJECT_ALIASES[name]
  if (alias) return alias
  const lower = name.toLowerCase()
  for (const item of parseWechatProjectCatalog(env)) {
    if (item.id === name || item.id.toLowerCase() === lower) return item.id
    if (item.label === name || item.label.toLowerCase() === lower) return item.id
  }
  return null
}

/** Explicit body projectId wins; otherwise per-user active project (default wechat). */
export function resolveWechatInboundProjectId(
  userId: string,
  explicitProjectId: string | undefined,
  env: NodeJS.ProcessEnv = process.env,
): string {
  const explicit = explicitProjectId?.trim()
  if (explicit) return explicit
  return getWechatActiveProjectId(userId, env)
}
