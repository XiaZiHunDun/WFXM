/**
 * Arch guard (D18-arch-align §17.3 脚手架修剪): 未接入生产调用链的
 * `package`（脚手架/归档）移入 `_archive/` 或删除，不在编译与测试
 * 白名单中。
 *
 * DESIGN §17.3 mandates that scaffolding / archived code must NOT
 * stay in the production workspace. Audit (D18, 2026-08-30) found 3
 * zero-importer packages under `packages/`:
 *   - `packages/migration/` — v4 → v5 migration tooling; 0 production
 *     importer (migration is run via scripts/CLI, not by runtime code).
 *   - `packages/config/` — placeholder package; 0 production importer.
 *   - `packages/shared/` — placeholder package; 0 production importer.
 * This guard LOCKS that future commits cannot leave a third-party
 * scaffolding package in the production workspace without an importer.
 *
 * Static checks (no runtime):
 *   - Every workspace package under `packages/<name>/` (excluding
 *     `_archive/`) must have at least 1 production-code importer
 *     (`packages/` or `apps/` source file importing from
 *     `@butler/<name>`). Zero importer = orphan = §17.3 violation.
 *
 * Remediation when this guard fires:
 *   1. Move the orphan package to `_archive/packages/<name>/`, OR
 *   2. Delete it (if no archived test depends on it), OR
 *   3. Wire a real production importer (commit that does so).
 *
 * Runtime behavior is verified by:
 *   - The 3 orphan packages (migration, config, shared) currently
 *     fail this guard. The guard's commit (D18) documents the
 *     remediation as a follow-up; until then, expect `pnpm test` to
 *     surface this guard as a known pending cleanup. The guard file
 *     itself skips those 3 packages via `KNOWN_ORPHANS` so existing
 *     tests stay green while the cleanup is pending.
 *
 * @deprecated after the orphan cleanup batch lands, the
 * `KNOWN_ORPHANS` allowlist must be removed.
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const PACKAGES_ROOT = join(__dirname, "../../packages")
const APPS_ROOT = join(__dirname, "../../apps")

/**
 * Pending cleanup: these workspace packages have 0 production importers
 * as of 2026-08-30. Until they are archived / deleted / wired, this
 * guard treats them as known orphans so existing tests stay green.
 * Remove this allowlist after the orphan-cleanup batch.
 */
const KNOWN_ORPHANS: ReadonlySet<string> = new Set([
  "migration",
  "config",
  "shared",
])

function listPackageNames(root: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(root)) {
    if (entry === "_archive" || entry.startsWith(".")) continue
    const p = join(root, entry)
    if (!statSync(p).isDirectory()) continue
    // Detect workspace package: must have package.json with `name` field.
    const pkgPath = join(p, "package.json")
    try {
      const pkg = JSON.parse(readFileSync(pkgPath, "utf-8")) as {
        name?: string
      }
      if (pkg.name && pkg.name.startsWith("@butler/")) {
        out.push(entry)
      }
    } catch {
      // not a package
    }
  }
  return out
}

function listProductionTsFiles(root: string): string[] {
  const out: string[] = []
  function walk(dir: string): void {
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry)
      const stat = statSync(p)
      if (stat.isDirectory()) {
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

describe("arch: §17.3 脚手架修剪 (no orphan workspace packages)", () => {
  it("every workspace package under packages/* (excluding _archive) has ≥1 production importer", () => {
    const pkgs = listPackageNames(PACKAGES_ROOT)
    expect(pkgs.length).toBeGreaterThan(0)
    const prodFiles = [
      ...listProductionTsFiles(PACKAGES_ROOT),
      ...listProductionTsFiles(APPS_ROOT),
    ]
    const newOrphans: string[] = []
    for (const pkg of pkgs) {
      if (KNOWN_ORPHANS.has(pkg)) continue // pending cleanup, see guard header
      let importers = 0
      for (const file of prodFiles) {
        const src = readFileSync(file, "utf-8")
        // Match `@butler/<pkg>` import (with or without subpath).
        const re = new RegExp(`from\\s+["']@butler/${pkg}(?:/|["'])`, "m")
        if (re.test(src)) importers += 1
      }
      if (importers === 0) {
        newOrphans.push(`${pkg} (importer_count=${importers})`)
      }
    }
    expect(
      newOrphans,
      `new orphan packages (move to _archive/ or wire a real importer): ${newOrphans.join(", ")}`,
    ).toEqual([])
  })

  it("known orphans (migration / config / shared) are still pending cleanup", () => {
    // This test documents the cleanup backlog. It fails if any known
    // orphan is removed without the allowlist being updated — i.e.,
    // catches accidental removal of the cleanup signal.
    const pkgs = listPackageNames(PACKAGES_ROOT)
    const stillOrphans: string[] = []
    const prodFiles = [
      ...listProductionTsFiles(PACKAGES_ROOT),
      ...listProductionTsFiles(APPS_ROOT),
    ]
    for (const pkg of KNOWN_ORPHANS) {
      if (!pkgs.includes(pkg)) continue
      let importers = 0
      for (const file of prodFiles) {
        const src = readFileSync(file, "utf-8")
        const re = new RegExp(`from\\s+["']@butler/${pkg}(?:/|["'])`, "m")
        if (re.test(src)) importers += 1
      }
      if (importers === 0) stillOrphans.push(pkg)
    }
    expect(
      stillOrphans,
      `known orphans moved out of packages/ without allowlist update: ${stillOrphans.join(", ")}`,
    ).toEqual(
      expect.arrayContaining(["migration", "config", "shared"]),
    )
  })
})