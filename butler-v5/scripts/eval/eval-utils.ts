/**
 * Shared helpers for the WFXM eval drivers (`run-task.ts` / `run-pi-task.ts`).
 * Kept free of side effects so either driver can import it safely.
 */
import { spawn, spawnSync } from "node:child_process"
import { mkdirSync, writeFileSync } from "node:fs"
import { dirname, isAbsolute, resolve } from "node:path"
import type { SeedFile } from "./task-input.js"

export interface DiffStats {
  readonly filesChanged: number
  readonly added: number
  readonly removed: number
}

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
