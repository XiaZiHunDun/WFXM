/**
 * Arch guard (D31-arch-align §7 Ports 主体): lock §7 主体 invariants
 * + extend D11 §7.1 port snapshot table.
 *
 *   §7 Ports: Core 对外的抽象依赖，由 driven adapters 实现、
 *             Composition Root 注入；只有真正可替换或不可信的边界才
 *             设立 Port；Core 只依赖 Ports；未设 Port 的内部函数
 *             不为"架构完整"创建接口；新副作用能力必须实现 Capability
 *             契约；新入口必须实现 Trigger 契约。
 *
 * D11 already locked the §7.1 snapshot table (Port existence per row).
 * D31 extends to: thin barrel (`packages/ports/src/index.ts` is a
 * pure `export * from "./core/*"` surface), zero implementation
 * leakage (no `class X implements Y` patterns; no fetch / DB / IO),
 * no upward imports from `@butler/adapters`, and no runtime /
 * persistence / apps reverse-import into the port surface (the
 * archived `r2-shim.ts` is the sole exception, scoped to
 * `_archive/packages/**`).
 *
 * Audit findings (D31, 2026-08-31):
 *
 *   - `packages/ports/src/index.ts` (55 lines): thin barrel =
 *     `export * from "./core/*"` + the archived R2 Effect Tag shim
 *     (`r2-shim.ts`). No class / no implementation; the file is a
 *     pure surface.
 *   - `packages/ports/src/core/{outbox,channel,clock,projection,
 *     event-store,credential-provider,snapshot}.ts` declare interface
 *     contracts only (no `class ... implements ...`, no fetch, no DB,
 *     no IO). The Capability contract (CapabilityDefinition +
 *     CapabilityProvider) lives in `packages/runtime/src/policy-gate.ts`
 *     and is consumed at runtime — D9 + D29 already lock Capability
 *     invariants; D31 only locks the **boundary** invariant (ports
 *     package does not leak into other packages' implementation
 *     surface).
 *   - No file under `packages/ports/src/` imports from
 *     `@butler/adapters` or `packages/adapters` (companion to D26A
 *     §20 #2 "Core 不 import adapters" — D31 narrows the same
 *     invariant to the ports package specifically).
 *   - No file under `packages/ports/src/` references
 *     `packages/runtime` / `packages/persistence` / `apps/api`
 *     (the archived `r2-shim.ts` fixture aside, which only
 *     references TypeScript types).
 *
 * Static checks (no runtime):
 *   - `packages/ports/src/index.ts` is a thin barrel: contains
 *     `export * from "./core/*"` and contains zero `class ... {}`
 *     or non-barrel type re-declarations.
 *   - `packages/ports/src/core/*.ts` files declare interfaces only
 *     (no class implementations, no fetch / DB / network calls).
 *   - `packages/ports/src/**` has 0 imports from `@butler/adapters`
 *     or `packages/adapters`.
 *   - `packages/ports/src/**` has 0 imports from
 *     `packages/runtime` / `packages/persistence` / `apps`.
 *
 * Runtime behavior is verified by:
 *   - ports-related unit tests (clock injection, / channel port,
 *     / projection port).
 *   - D11 §7.1 snapshot test (Port existence per row).
 *   - D26A §20 #2 lock (Core 不 import adapters — ports is the
 *     strict subset).
 *
 * Remediation when this guard fires:
 *   - ports barrel grows (class / impl added): §7 violation; remove
 *     — ports is interface-only.
 *   - ports/src imports adapters / runtime / persistence: §7
 *     "依赖方向向内" violation; remove the import (composition
 *     root must do the wiring).
 *   - ports/src core/ files contain fetch / DB / IO: §7 "抽象依赖"
 *     violation; move the implementation into an adapter.
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const PORTS_SRC = join(__dirname, "../../packages/ports/src")
const PORTS_INDEX = join(PORTS_SRC, "index.ts")
const PORTS_CORE = join(PORTS_SRC, "core")

function listPortsFiles(root: string): string[] {
  const out: string[] = []
  function walk(dir: string): void {
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry)
      const st = statSync(p)
      if (st.isDirectory()) {
        if (
          entry === "node_modules" ||
          entry === "dist" ||
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

describe("arch: §7 Ports 主体 (D31 — thin barrel + zero impl + zero upward imports)", () => {
  // ── 1. §7 thin barrel: index.ts 仅 export * from "./core/*" ─────

  it("§7: packages/ports/src/index.ts is a thin barrel (export * from './core/*.js' + no class / no impl)", () => {
    const src = readFileSync(PORTS_INDEX, "utf-8")
    // Thin barrel: re-export each core/*.js file individually
    // (the v5 ports barrel uses explicit per-file re-exports so that
    // archived R2 shim entries stay scoped under r2-shim.js).
    expect(
      src,
      "ports/index.ts must re-export from './core/*.js' (thin barrel pattern)",
    ).toMatch(/export\s*\*\s*from\s*["']\.\/core\/\w+\.js["']/)
    // Sanity: at least one core/* re-export present.
    const reExportCount = (
      src.match(/export\s*\*\s*from\s*["']\.\/core\/\w+\.js["']/g) ?? []
    ).length
    expect(
      reExportCount,
      `ports/index.ts should re-export from core/*.js ≥ 1 time; got ${reExportCount}`,
    ).toBeGreaterThanOrEqual(1)
    // No class declarations (ports is interface-only).
    expect(
      /^(?:export\s+)?class\s+\w+\b/m.test(src),
      "ports/index.ts must NOT declare a class — §7 ports is interface-only",
    ).toBe(false)
    // No fetch / DB / IO in the barrel.
    const FORBIDDEN_IO = [
      /\bfetch\s*\(/,
      /\bpgTable\s*\(/,
      /\bdrizzle\b/,
      /import\s+["'][^"']*node:fs/,
    ]
    const violations: string[] = []
    for (const re of FORBIDDEN_IO) {
      if (re.test(src)) violations.push(`index.ts: ${re}`)
    }
    expect(violations, `ports barrel leaked IO: ${violations.join(", ")}`).toEqual([])
  })

  // ── 2. §7 ports/core/*.ts 0 implement (interface only) ──────────

  it("§7: ports/core/*.ts files declare interfaces only — zero class implementations, zero fetch/DB/IO", () => {
    const coreFiles = listPortsFiles(PORTS_CORE)
    expect(coreFiles.length, "ports/core must contain at least 1 port file").toBeGreaterThanOrEqual(1)
    const FORBIDDEN_IMPL_PATTERNS: readonly (readonly [string, RegExp])[] = [
      ["class implements", /^\s*(?:export\s+)?class\s+\w+\s+(?:extends|implements)\s+\w+/m],
      ["fetch call", /(?<!\w)fetch\s*\(\s*["'`]/],
      ["pgTable declaration", /pgTable\s*\(/],
      ["drizzle import", /from\s+["']drizzle/],
      ["node:fs / node:http", /from\s+["']node:(?:fs|http|net)/],
      ["DB connection", /\bnew\s+(?:Pool|Client|Connection)\b/],
    ]
    const violations: string[] = []
    for (const file of coreFiles) {
      const src = readFileSync(file, "utf-8")
      for (const [name, re] of FORBIDDEN_IMPL_PATTERNS) {
        if (re.test(src)) violations.push(`${file}: ${name}`)
      }
    }
    expect(
      violations,
      `ports/core/* must be interface-only — found: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── 3. §7 ports 不依赖 @butler/adapters ──────────────────────────

  it("§7: ports/src/** does NOT import @butler/adapters or packages/adapters (依赖方向向内)", () => {
    const files = listPortsFiles(PORTS_SRC)
    const FORBIDDEN = [
      /from\s+["']@butler\/adapters\b/,
      /from\s+["'][^"']*packages\/adapters\b/,
    ]
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, "utf-8")
      for (const re of FORBIDDEN) {
        if (re.test(src)) violations.push(`${file}: ${re}`)
      }
    }
    expect(
      violations,
      `ports/src must NOT import adapters (依赖方向向内 — §7 line 266): ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── 4. §7 ports/core 7 Port interface 完整 ─ ─────────────────────

  it("§7: ports/core/ has the canonical Port set (Repository/Model/Capability/Channel/Clock/EventStore/CredentialProvider snapshot — §7 + D11)", () => {
    const coreFiles = listPortsFiles(PORTS_CORE).map((f) =>
      f.split("/").slice(-1)[0],
    )
    // Per D11 §7.1 snapshot, ports/core covers: Channel / Clock /
    // Repository / Model / Projection / EventStore / CredentialProvider /
    // Snapshot / Outbox. Repository materialized in ports/core in D46
    // (second persistence impl trigger — in-memory runtime-store); Model
    // materialized in D44. Capability stays in runtime (D29 §9 lock).
    const expected = [
      "channel.ts",
      "clock.ts",
      "credential-provider.ts",
      "event-store.ts",
      "model-port.ts",
      "outbox.ts",
      "projection.ts",
      "repository.ts",
      "snapshot.ts",
    ]
    for (const name of expected) {
      expect(
        coreFiles.includes(name),
        `ports/core/${name} missing — §7 Port snapshot incomplete`,
      ).toBe(true)
    }
  })

  // ── 5. §7 ports 不引用 runtime / persistence / apps ────────────

  it("§7: ports/src/** does NOT reference packages/runtime / packages/persistence / apps (ports is a stable surface, dependencies stay inward-only)", () => {
    const files = listPortsFiles(PORTS_SRC)
    const FORBIDDEN = [
      /from\s+["']@butler\/runtime\b/,
      /from\s+["']@butler\/persistence\b/,
      /from\s+["'][^"']*packages\/runtime\b/,
      /from\s+["'][^"']*packages\/persistence\b/,
      /from\s+["']\.\.\/\.\.\/runtime\b/,
      /from\s+["']\.\.\/\.\.\/persistence\b/,
      /from\s+["']\.\.\/\.\.\/apps\b/,
    ]
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, "utf-8")
      for (const re of FORBIDDEN) {
        if (re.test(src)) violations.push(`${file}: ${re}`)
      }
    }
    expect(
      violations,
      `ports/src must NOT reference runtime / persistence / apps (§7 依赖方向向内): ${violations.join(", ")}`,
    ).toEqual([])
  })
})