/**
 * Arch guard (D32-arch-align §17.1 包归属与依赖方向 + §17.2 并行开发边界):
 * lock §17.1 (pnpm workspace + turbo monorepo with 5-band topology) +
 * §17.2 (parallel dev boundaries per band).
 *
 *   §17.1 — pnpm workspace + turbo TS monorepo; 5 bands (driving /
 *             core / ports / driven / config-shared); dependency
 *             direction matches runtime architecture; only production
 *             call chain + ports + driving adapters remain.
 *   §17.2 — once Port contracts are stable, the 3 bands can develop
 *             in parallel: driving adapter side / driven adapter side
 *             / runtime+domain. Schema changes are isolated to
 *             persistence; new entry points must implement Trigger;
 *             new side effects must implement Capability.
 *
 * D18 + D19 already locked §4 (5 聚合 PASS) + §17.3 (5 active
 * packages, _archive/ excluded). D26A locked §20 #2 "Core 不 import
 * adapters". D31 locked ports boundary. D32 extends to §17.1
 * workspace topology + §17.2 parallel-dev boundaries.
 *
 * Audit findings (D32, 2026-08-31):
 *
 *   - pnpm-workspace.yaml covers exactly 3 globs: `packages/*`,
 *     `apps/*`, `cli` (the canonical driving surface). 5 active
 *     packages under `packages/*` (adapters / domain / persistence
 *     / ports / runtime) match §20 #16 invariant.
 *   - turbo.json is present (build / test pipeline orchestrator).
 *   - Core packages (runtime + domain) do NOT import adapters /
 *     persistence implementations (D26A §20 #2 — same invariant
 *     restated under §17.1 framing).
 *   - §17.2 parallel-dev band 1 (driving adapter): apps/api entry
 *     points (wechat / cli / schedule / task / channel-inbound /
 *     routes) import from ports + domain + runtime (not from
 *     adapters / persistence internal surfaces).
 *   - §17.3: `vitest.config.ts` (production config) excludes
 *     `_archive/` (D19 + D18). Archived tests live under
 *     `vitest.archived.config.ts` — separate runner, separate
 *     CI gate.
 *
 * Static checks (no runtime):
 *   - `pnpm-workspace.yaml` lists exactly `packages/*`, `apps/*`,
 *     `cli`.
 *   - `turbo.json` is present at workspace root.
 *   - 5 active packages under `packages/` (adapters / domain /
 *     persistence / ports / runtime) match §17.1.
 *   - No Core package imports `@butler/adapters` or `packages/adapters`
 *     (D26A #2 — re-locked under §17.1 framing).
 *   - `vitest.config.ts` excludes `_archive/` (production tests do
 *     not pick up archived scaffolding).
 *
 * Runtime behavior is verified by:
 *   - vitest.archived.config.ts separately runs archived tests
 *     (101 tests, D19 baseline).
 *   - D26A §20 #2 lock (Core 不 import adapters) — companion.
 *   - D19 §17.3 + D18 §4 — 5 active packages invariant.
 *
 * Remediation when this guard fires:
 *   - 4th band added to workspace.yaml without DESIGN §17.1 update:
 *     revert and add to §17.1 table first.
 *   - turbo.json removed: §17.1 "turbo 的 TS monorepo" violation;
 *     restore.
 *   - Core package imports adapters: §17.1 "依赖方向" + §17.2
 *     "Core 不被反向依赖" violation; remove the import.
 *   - vitest.config.ts pulls in _archive/: §17.3 violation;
 *     exclude (use vitest.archived.config.ts for archived tests).
 */

import { describe, expect, it } from "vitest"
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const REPO_ROOT = join(__dirname, "../..")
const WORKSPACE_YAML = join(REPO_ROOT, "pnpm-workspace.yaml")
const TURBO_JSON = join(REPO_ROOT, "turbo.json")
const PACKAGES = join(REPO_ROOT, "packages")
const VITEST_CONFIG = join(REPO_ROOT, "vitest.config.ts")

const EXPECTED_ACTIVE_PACKAGES: readonly string[] = [
  "adapters",
  "domain",
  "persistence",
  "ports",
  "runtime",
]

function listDirs(root: string): string[] {
  if (!existsSync(root)) return []
  return readdirSync(root).filter((e) => {
    const p = join(root, e)
    if (!statSync(p).isDirectory()) return false
    if (e === "node_modules" || e === "_archive" || e.startsWith(".")) {
      return false
    }
    return true
  })
}

describe("arch: §17.1 包归属与依赖方向 + §17.2 并行开发边界 (D32)", () => {
  // ── §17.1 1. pnpm-workspace.yaml 3 glob ────────────────────────

  it("§17.1: pnpm-workspace.yaml lists exactly 3 globs (packages/* + apps/* + cli)", () => {
    const src = readFileSync(WORKSPACE_YAML, "utf-8")
    expect(src).toMatch(/^\s*-\s*["']packages\/\*["']/m)
    expect(src).toMatch(/^\s*-\s*["']apps\/\*["']/m)
    expect(src).toMatch(/^\s*-\s*["']cli["']/m)
    // No additional globs silently added.
    const globCount = (src.match(/^\s*-\s*["'][^"']+["']/gm) ?? []).length
    expect(globCount, `pnpm-workspace.yaml globs = ${globCount}; want exactly 3`).toBe(3)
  })

  // ── §17.1 2. turbo.json present ────────────────────────────────

  it("§17.1: turbo.json exists at workspace root (build/test pipeline orchestrator)", () => {
    expect(
      existsSync(TURBO_JSON),
      "turbo.json must exist at workspace root — §17.1 mandates pnpm workspace + turbo TS monorepo",
    ).toBe(true)
  })

  // ── §17.1 3. 5 active packages under packages/* ──────────────

  it("§17.1: packages/ has exactly 5 active packages matching the §17.1 Core/Driven band table", () => {
    const dirs = listDirs(PACKAGES)
    expect(
      dirs.sort(),
      `packages/* active dirs = ${dirs.join(", ")}; want exactly ${EXPECTED_ACTIVE_PACKAGES.join(", ")}`,
    ).toEqual([...EXPECTED_ACTIVE_PACKAGES].sort())
  })

  // ── §17.1 4. Core 不 import adapters ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

  it("§17.1 + §17.2: Core packages (runtime + domain) do NOT import adapters (依赖方向 + Core 不被反向依赖)", () => {
    const coreDirs = [join(PACKAGES, "runtime"), join(PACKAGES, "domain")]
    const violations: string[] = []
    const FORBIDDEN = [
      /from\s+["']@butler\/adapters\b/,
      /from\s+["'][^"']*packages\/adapters\b/,
      /from\s+["']\.\.\/adapters\b/,
    ]
    for (const dir of coreDirs) {
      if (!existsSync(dir)) continue
      for (const file of listProductionTs(dir)) {
        const src = readFileSync(file, "utf-8")
        for (const re of FORBIDDEN) {
          if (re.test(src)) violations.push(`${file}: ${re}`)
        }
      }
    }
    expect(
      violations,
      `Core packages must NOT import adapters (§17.1 + D26A §20 #2): ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── §17.3 5. _archive 不进入 prod 测试白名单 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

  it("§17.3: production vitest.config.ts excludes _archive/ (archived scaffolding has its own runner)", () => {
    expect(existsSync(VITEST_CONFIG), "vitest.config.ts must exist").toBe(true)
    const src = readFileSync(VITEST_CONFIG, "utf-8")
    // Production config must exclude _archive/ explicitly (D19 baseline).
    expect(
      src,
      "vitest.config.ts must reference _archive in its exclude list — §17.3 hygiene invariant",
    ).toMatch(new RegExp("_archive/"))
  })
})

function listProductionTs(root: string): string[] {
  const out: string[] = []
  function walk(dir: string): void {
    if (!existsSync(dir)) return
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry)
      const st = statSync(p)
      if (st.isDirectory()) {
        if (
          entry === "node_modules" ||
          entry === "dist" ||
          entry === "_archive" ||
          entry === "coverage" ||
          entry.startsWith(".")
        ) {
          continue
        }
        walk(p)
      } else if (
        entry.endsWith(".ts") &&
        !entry.endsWith(".test.ts") &&
        !entry.endsWith(".d.ts")
      ) {
        out.push(p)
      }
    }
  }
  walk(root)
  return out
}