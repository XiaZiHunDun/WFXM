/**
 * Shared helpers for the WFXM eval drivers (`run-task.ts` / `run-pi-task.ts`).
 * Kept free of side effects so either driver can import it safely.
 */
import { spawn, spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path"
import type { SeedFile } from "./task-input.js"

export interface DiffStats {
  readonly filesChanged: number
  readonly added: number
  readonly removed: number
}

export interface WorkspaceFileSnapshot {
  readonly hash: string
  readonly lines: number
  /** 文本内容；二进制或超大文件为 null。 */
  readonly text: string | null
}

export type WorkspaceSnapshot = Map<string, WorkspaceFileSnapshot>

export interface WorkspaceChange {
  readonly path: string
  readonly change: "added" | "modified" | "deleted"
  readonly added: number
  readonly removed: number
}

export interface WorkspaceDiff {
  readonly changes: readonly WorkspaceChange[]
  readonly baselineHash: string
  readonly workspaceHash: string
}

const SNAPSHOT_SKIP_DIRS = new Set([
  ".git",
  "node_modules",
  ".pnpm-store",
  "dist",
  "coverage",
  ".cache",
  ".eval",
  ".turbo",
])

const MAX_TEXT_BYTES = 1_000_000

export interface TestRun {
  readonly command: string
  readonly exitCode: number
  readonly passed: boolean
  readonly results: readonly { readonly name: string; readonly ok: boolean }[]
  readonly outputTail: string
}

export function emitResult(result: Record<string, unknown>): void {
  process.stdout.write(`\n__EVAL_RESULT__${JSON.stringify(result)}\n`)
}

/** 解析工作区内的相对路径；拒绝绝对路径与 `..`，保持评估可控。 */
export function resolveInsideWorkspace(workspaceRoot: string, path: string): string {
  const segments = path.split(/[\\/]/)
  if (isAbsolute(path) || segments.includes("..")) {
    throw new Error(`路径必须位于工作区内：${path}`)
  }
  return resolve(workspaceRoot, path)
}

/**
 * repo-task 的变更规模：对夹具目录与终态工作区做 numstat。
 * 只统计行级 diff，不把测试产物或绝对路径带进报告。
 */
export function diffWorkspace(beforeRoot: string, afterRoot: string): DiffStats | null {
  const result = spawnSync(
    "git",
    ["diff", "--no-index", "--numstat", "--", beforeRoot, afterRoot],
    { encoding: "utf8", maxBuffer: 8 * 1024 * 1024 },
  )
  if (result.error || typeof result.stdout !== "string") return null
  let filesChanged = 0
  let added = 0
  let removed = 0
  for (const line of result.stdout.split("\n")) {
    if (!line.trim()) continue
    const [addedRaw, removedRaw] = line.split("\t")
    if (addedRaw === undefined || removedRaw === undefined) continue
    filesChanged += 1
    if (/^\d+$/.test(addedRaw)) added += Number(addedRaw)
    if (/^\d+$/.test(removedRaw)) removed += Number(removedRaw)
  }
  return { filesChanged, added, removed }
}

/** 在沙箱工作区预置文件。 */
export function seedWorkspace(workspaceRoot: string, files: readonly SeedFile[]): void {
  for (const file of files) {
    const abs = resolveInsideWorkspace(workspaceRoot, file.path)
    mkdirSync(dirname(abs), { recursive: true })
    writeFileSync(abs, file.content, "utf8")
  }
}

/**
 * 工作区快照：路径 → 内容哈希 + 行数。
 *
 * 防作弊层依赖它判断“测试/配置是否被改过”，质量门禁依赖它统计改动面。
 * 跳过依赖、构建产物与 VCS 目录；二进制只保留哈希。
 */
export function snapshotWorkspace(root: string): WorkspaceSnapshot {
  const out: WorkspaceSnapshot = new Map()
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isSymbolicLink()) continue
      const abs = join(dir, entry.name)
      if (entry.isDirectory()) {
        if (!SNAPSHOT_SKIP_DIRS.has(entry.name)) walk(abs)
        continue
      }
      if (!entry.isFile()) continue
      const path = relative(root, abs).split(sep).join("/")
      const buffer = readFileSync(abs)
      const binary = buffer.includes(0)
      const text = binary || buffer.byteLength > MAX_TEXT_BYTES ? null : buffer.toString("utf8")
      out.set(path, {
        hash: createHash("sha256").update(buffer).digest("hex"),
        lines: text === null ? 0 : countLines(text),
        text,
      })
    }
  }
  walk(root)
  return out
}

function countLines(text: string): number {
  if (text.length === 0) return 0
  let lines = text.split("\n").length
  if (text.endsWith("\n")) lines -= 1
  return lines
}

/** 行级差异；文件较小时用 LCS，避免只按行数差误判“替换一行”。 */
function lineDiff(
  before: readonly string[],
  after: readonly string[],
): { added: number; removed: number } {
  if (before.length === 0) return { added: after.length, removed: 0 }
  if (after.length === 0) return { added: 0, removed: before.length }
  if (before.length * after.length > 4_000_000) {
    const delta = after.length - before.length
    return delta >= 0 ? { added: delta, removed: 0 } : { added: 0, removed: -delta }
  }
  const width = after.length + 1
  let prev = new Uint32Array(width)
  let current = new Uint32Array(width)
  for (let i = 1; i <= before.length; i += 1) {
    for (let j = 1; j <= after.length; j += 1) {
      current[j] =
        before[i - 1] === after[j - 1]
          ? (prev[j - 1] ?? 0) + 1
          : Math.max(prev[j] ?? 0, current[j - 1] ?? 0)
    }
    const swap = prev
    prev = current
    current = swap
    current.fill(0)
  }
  const common = prev[after.length] ?? 0
  return { added: after.length - common, removed: before.length - common }
}

function snapshotDigest(snapshot: WorkspaceSnapshot): string {
  const hash = createHash("sha256")
  for (const path of [...snapshot.keys()].sort()) {
    hash.update(`${path}:${snapshot.get(path)?.hash ?? ""}\n`)
  }
  return `sha256:${hash.digest("hex")}`
}

/** 对比前后快照，只返回变更文件与行级规模。 */
export function diffWorkspaceSnapshots(
  before: WorkspaceSnapshot,
  after: WorkspaceSnapshot,
): WorkspaceDiff {
  const paths = new Set([...before.keys(), ...after.keys()])
  const changes: WorkspaceChange[] = []
  for (const path of [...paths].sort()) {
    const prev = before.get(path)
    const next = after.get(path)
    if (prev === undefined && next === undefined) continue
    if (prev === undefined && next !== undefined) {
      changes.push({ path, change: "added", added: next.lines, removed: 0 })
      continue
    }
    if (prev !== undefined && next === undefined) {
      changes.push({ path, change: "deleted", added: 0, removed: prev.lines })
      continue
    }
    if (prev?.hash === next?.hash) continue
    const beforeLines = prev?.text?.split("\n") ?? []
    const afterLines = next?.text?.split("\n") ?? []
    const { added, removed } = lineDiff(beforeLines, afterLines)
    changes.push({ path, change: "modified", added, removed })
  }
  return {
    changes,
    baselineHash: snapshotDigest(before),
    workspaceHash: snapshotDigest(after),
  }
}

/** 解析 TAP 的 `ok/not ok N - name` 行；非 TAP 输出返回空数组。 */
export function parseTap(output: string): { name: string; ok: boolean }[] {
  const results: { name: string; ok: boolean }[] = []
  for (const raw of output.split("\n")) {
    const match = /^(not ok|ok)\s+\d+\s+-\s+(.+?)(?:\s+#.*)?$/.exec(raw.trim())
    if (match?.[2]) results.push({ name: match[2], ok: match[1] === "ok" })
  }
  return results
}

/** 独立运行测试命令；oracle 放在驱动侧，避免 agent 自证。 */
export function runTests(
  cwd: string,
  spec: { command: string; timeoutMs?: number },
): Promise<TestRun> {
  return new Promise((resolvePromise) => {
    const child = spawn("bash", ["-lc", spec.command], {
      cwd,
      env: { ...process.env, NODE_ENV: "test" },
    })
    let output = ""
    let settled = false
    const finish = (code: number, tail = ""): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolvePromise({
        command: spec.command,
        exitCode: code,
        passed: code === 0,
        results: parseTap(output),
        outputTail: `${output}\n${tail}`.trim().slice(-2000),
      })
    }
    const append = (chunk: Buffer): void => {
      output += chunk.toString()
      if (output.length > 20_000) output = output.slice(-20_000)
    }
    child.stdout.on("data", append)
    child.stderr.on("data", append)
    child.on("error", (err: Error) => finish(1, err.message))
    child.on("close", (code) => finish(code ?? 1))
    const timer = setTimeout(() => child.kill("SIGKILL"), spec.timeoutMs ?? 60_000)
  })
}
