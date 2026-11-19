// 共享 fixture：只负责临时工作区（root + 越界目录）的创建/清理与常用写盘。
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"

export const READ_LIMIT_BYTES = 64 * 1024
export const COMMAND_OUTPUT_LIMIT_BYTES = 32 * 1024

export interface TempWorkspace {
  readonly root: string
  readonly outside: string
  cleanup(): void
}

export function makeTempWorkspace(prefix = "tool-contract-"): TempWorkspace {
  const root = mkdtempSync(join(tmpdir(), `${prefix}root-`))
  const outside = mkdtempSync(join(tmpdir(), `${prefix}outside-`))
  return {
    root,
    outside,
    cleanup() {
      rmSync(root, { recursive: true, force: true })
      rmSync(outside, { recursive: true, force: true })
    },
  }
}

export function writeText(root: string, rel: string, content: string): string {
  const path = join(root, rel)
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, content, "utf8")
  return path
}

export function writeBytes(root: string, rel: string, bytes: Buffer): string {
  const path = join(root, rel)
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, bytes)
  return path
}

/** 在 root 内创建一个指向 outside 的符号链接（用于越界符号链接边界）。 */
export function makeEscapeSymlink(workspace: TempWorkspace, name = "escape-link.txt"): string {
  const secret = join(workspace.outside, "secret.txt")
  writeFileSync(secret, "outside-secret", "utf8")
  const link = join(workspace.root, name)
  symlinkSync(secret, link)
  return link
}
