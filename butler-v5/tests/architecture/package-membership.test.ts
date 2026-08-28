// tests/architecture/package-membership.test.ts
//
// 守卫 DESIGN §17.3 / invariant 16：
// monorepo 仅生产调用链 + 端口 + 单一 schema；脚手架归档。
//
// 测试 4 件事：
//  (1) production source 不得真的 import _archive/（import / require /
//      dynamic import 才算违反；注释/文档提及不计入）
//  (2) pnpm-workspace.yaml 不得 glob _archive
//  (3) vitest.config.ts 不得 include _archive（exclude 是 expected）
//  (4) ports/src/index.ts Effect Tag 类在 postgres 适配器完全迁移到 /core/*
//      之前必须保留——本测试是 reminder（防误删），迁移完成后改写/移除

import { describe, it, expect } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"

const REPO_ROOT = "/home/ailearn/projects/WFXM"
const BUTLER_V5 = join(REPO_ROOT, "butler-v5")

const PRODUCTION_SOURCE_DIRS = [
  "packages/runtime/src",
  "packages/adapters/src",
  "packages/persistence/src",
  "packages/domain/src",
  "packages/ports/src",
  "apps/api/src",
  "apps/cli/src",
  "cli/src",
] as const

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[]
  try {
    entries = readdirSync(dir)
  } catch {
    return out
  }
  for (const name of entries) {
    const full = join(dir, name)
    let st
    try {
      st = statSync(full)
    } catch {
      continue
    }
    if (st.isDirectory()) {
      if (name === "node_modules" || name === "_archive" || name === "dist" || name === "coverage") {
        continue
      }
      walk(full, out)
    } else if (st.isFile()) {
      if (/\.(ts|tsx|mjs|cjs)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) {
        out.push(full)
      }
    }
  }
  return out
}

/** strip line/block comments so doc references don't trip the detector */
function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "")
}

/** real code-level reference into _archive/ (after comments stripped) */
function hasArchiveImport(text: string): boolean {
  const code = stripComments(text)
  const patterns = [
    /\bfrom\s+['"]([^'"]*_archive\/[^'"]*)['"]/,
    /\brequire\s*\(\s*['"]([^'"]*_archive\/[^'"]*)['"]\)/,
    /\bimport\s*\(\s*['"]([^'"]*_archive\/[^'"]*)['"]\)/,
  ]
  return patterns.some((re) => re.test(code))
}

describe("package-membership (DESIGN invariant 16)", () => {
  it("(1) production source never imports into _archive/", () => {
    const violations: string[] = []
    for (const rel of PRODUCTION_SOURCE_DIRS) {
      const abs = join(BUTLER_V5, rel)
      for (const file of walk(abs)) {
        const text = readFileSync(file, "utf8")
        if (hasArchiveImport(text)) {
          violations.push(relative(REPO_ROOT, file))
        }
      }
    }
    expect(
      violations,
      `Found _archive/ imports (comments already stripped):\n${violations.join("\n")}`,
    ).toEqual([])
  })

  it("(2) pnpm-workspace.yaml does not glob _archive", () => {
    const ws = readFileSync(join(BUTLER_V5, "pnpm-workspace.yaml"), "utf8")
    expect(ws).not.toMatch(/_archive/)
  })

  it("(3) vitest.config.ts only EXCLUDES (not INCLUDES) _archive paths", () => {
    const cfg = readFileSync(join(BUTLER_V5, "vitest.config.ts"), "utf8")
    // Acceptable: an `exclude:` glob listing _archive.
    // Unacceptable: an `include:` glob (or test.include) that pulls in _archive tests.
    if (/_archive/.test(cfg)) {
      // _archive must be referenced inside an `exclude:` pattern (excluding it from collection).
      // Any other position (include / test.include) is a violation of invariant 16.
      const hasExcludeContext = /exclude:[\s\S]*?_archive/.test(cfg)
      expect(
        hasExcludeContext,
        "vitest.config.ts mentions _archive; it must be referenced inside an 'exclude:' pattern, not include / test.include.",
      ).toBe(true)
    }
    // no _archive in file → trivially OK
  })

  it("(4) ports/src/index.ts thin barrel — R2 Effect Tag classes 已经归档（R12, 2026-08-28）", () => {
    const ix = readFileSync(
      join(BUTLER_V5, "packages/ports/src/index.ts"),
      "utf8",
    )
    // R12: 全部 14 R2 Effect Tag 类与 postgres 适配器一并清理；本测试断言反例。
    expect(ix, "EventStoreService must NOT be present (R12 archived to _archive)").not.toMatch(
      /export class EventStoreService/,
    )
    expect(ix, "OutboxService must NOT be present (R12 archived to _archive)").not.toMatch(
      /export class OutboxService/,
    )
    expect(ix, "SnapshotService must NOT be present (R12 archived to _archive)").not.toMatch(
      /export class SnapshotService/,
    )
  })
})
