/**
 * Arch guard (D25-arch-align §5 Domain 纯规则层): lock Domain 包
 * 4 项 invariants:
 *
 *   1. **Pure with impure fallback** (D25 owner 拍板): Domain pure
 *      functions accept `input.nowMs ?? Date.now()` /
 *      `input.id ?? crypto.randomUUID()` so callers can inject a
 *      fixed clock / id for deterministic tests. Without caller
 *      injection the function still produces a value (impure), but
 *      test paths pass `nowMs` / `id` and stay deterministic. This
 *      pattern is the §5 pure-functionality escape hatch — Domain
 *      remains free of I/O (network / file / DB / channel / LLM),
 *      the only impure calls are local `Date.now` /
 *      `crypto.randomUUID`, and only as fallbacks.
 *   2. **No LLM call** (§5 line 183): no `import` of `LLMAdapter`
 *      or `@butler/adapters/...` from `packages/domain/src/**`.
 *      Comment-only references are allowed.
 *   3. **4 范围 path existence** (§5 line 178-181):
 *      - 聚合类型与状态机 → `packages/domain/src/{knowledge,conversation,projects}/`
 *      - 工作集预算与截断策略 → `packages/runtime/src/working-set.ts`
 *      - ActionRequest 构造与参数摘要 → `packages/runtime/src/capability-boundary.ts`
 *      - 可重放的确定性决策 (Policy 规则) → `packages/domain/src/{permissions,guards,memory,tools,projects}/pure.ts`
 *   4. **No infra cross-package imports** (D17 inherited): Domain
 *      must not import from `ports`, `adapters`, `application`, or
 *      `infrastructure`. Already covered by
 *      `tests/architecture/domain-zero-io.test.ts`; this case
 *      re-locks the invariant under §5 framing.
 *
 * Static checks (no runtime):
 *   - Domain `.ts` files contain ≥5 occurrences of
 *     `input.nowMs ?? Date.now()` and ≥5 of
 *     `input.id ?? crypto.randomUUID()` (the §5 impure-fallback
 *     pattern, persisted across D-series audits).
 *   - Domain `.ts` files have 0 non-comment `import` of
 *     `LLMAdapter` / `@butler/adapters/llm-provider`.
 *   - 4 §5 范围 paths exist on disk.
 *
 * Runtime behavior is verified by:
 *   - `tests/architecture/domain-zero-io.test.ts` (D17 pre-existing).
 *   - The Domain unit tests themselves (each pure function has a
 *     deterministic test suite that exercises `nowMs` /
 *     `id` injection paths).
 *
 * Remediation when this guard fires:
 *   - Pure-with-impure-fallback count drops below threshold:
 *     refactoring accidentally moved the pattern out of Domain. Move
 *     the fallback back into the pure function so callers can opt in
 *     to a fixed clock.
 *   - LLMAdapter import appears in Domain: §5 line 183 violation;
 *     delete the import or move the consumer to runtime / apps.
 *   - 4 范围 paths missing: §5 范围 drift; recover via the same
 *     D19 orphan cleanup pattern.
 */

import { describe, expect, it } from "vitest"
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs"
import { join } from "node:path"

const DOMAIN_SRC = join(__dirname, "../../packages/domain/src")
const RUNTIME_SRC = join(__dirname, "../../packages/runtime/src")

function listDomainTs(): string[] {
  const out: string[] = []
  function walk(dir: string): void {
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry)
      const st = statSync(p)
      if (st.isDirectory()) walk(p)
      else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p)
    }
  }
  walk(DOMAIN_SRC)
  return out
}

describe("arch: §5 Domain 纯规则层 (D25 audit — pure + impure fallback pattern)", () => {
  // ── 1. Pure with impure fallback pattern persists ────────────

  it("Domain pure functions retain the `input.nowMs ?? Date.now()` impure-fallback pattern", () => {
    const files = listDomainTs()
    const re = /input\.nowMs\s*\?\?\s*Date\.now\(\)/
    const hits = files.filter((f) => re.test(readFileSync(f, "utf-8")))
    expect(
      hits.length,
      `Domain files using input.nowMs ?? Date.now() = ${hits.length}; want ≥ 5 (D25 lock current conformance — caller-injectable clock pattern)`,
    ).toBeGreaterThanOrEqual(5)
  })

  it("Domain pure functions retain the `input.id ?? crypto.randomUUID()` impure-fallback pattern", () => {
    const files = listDomainTs()
    const re = /input\.id\s*\?\?\s*crypto\.randomUUID\(\)/
    const hits = files.filter((f) => re.test(readFileSync(f, "utf-8")))
    expect(
      hits.length,
      `Domain files using input.id ?? crypto.randomUUID() = ${hits.length}; want ≥ 5 (D25 lock current conformance — caller-injectable id pattern)`,
    ).toBeGreaterThanOrEqual(5)
  })

  // ── 2. No LLMAdapter import in Domain ────────────────────────

  it("Domain does NOT import LLMAdapter (non-comment); §5 line 183 — Domain 不直接调用 LLM", () => {
    const files = listDomainTs()
    const importRe =
      /from\s+["'][^"']*(LLMAdapter|llm-provider)[^"']*["']|import\s+type\s*\{[^}]*LLMAdapter[^}]*\}\s*from/
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, "utf-8")
      // Strip block + line comments so doc-comment references to
      // LLMAdapter (e.g. local-trace.ts:15) do not count.
      const stripped = src
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "")
      if (importRe.test(stripped)) {
        violations.push(file)
      }
    }
    expect(
      violations,
      `Domain files with non-comment LLMAdapter import: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── 3. §5 4 范围 paths exist ──────────────────────────────────

  it("§5 范围 1: 聚合类型与状态机 (domain knowledge + conversation + projects)", () => {
    const paths = [
      join(DOMAIN_SRC, "knowledge"),
      join(DOMAIN_SRC, "conversation"),
      join(DOMAIN_SRC, "projects"),
    ]
    for (const p of paths) {
      expect(existsSync(p), `${p} missing — §5 聚合类型与状态机 drift`).toBe(true)
    }
  })

  it("§5 范围 2: 工作集预算与截断策略 (runtime working-set.ts)", () => {
    expect(
      existsSync(join(RUNTIME_SRC, "working-set.ts")),
      "runtime/working-set.ts missing — §5 工作集预算 drift",
    ).toBe(true)
  })

  it("§5 范围 3: ActionRequest 构造与参数摘要 (runtime capability-boundary.ts)", () => {
    const path = join(RUNTIME_SRC, "capability-boundary.ts")
    expect(existsSync(path), `${path} missing — §5 ActionRequest/digest drift`).toBe(true)
    // digest computation must be present in capability-boundary.ts.
    const src = readFileSync(path, "utf-8")
    expect(src).toMatch(/digest/i)
  })

  it("§5 范围 4: 可重放的确定性决策 / Policy 规则 (domain *pure.ts files)", () => {
    const pureFiles = [
      join(DOMAIN_SRC, "permissions/pure.ts"),
      join(DOMAIN_SRC, "guards/pure.ts"),
      join(DOMAIN_SRC, "memory/pure.ts"),
      join(DOMAIN_SRC, "tools/pure.ts"),
      join(DOMAIN_SRC, "projects/pure.ts"),
    ]
    for (const p of pureFiles) {
      expect(existsSync(p), `${p} missing — §5 Policy pure rules drift`).toBe(true)
    }
  })

  // ── 4. Domain stays free of cross-package infra imports ───────

  it("Domain does not import from ports / adapters / application / infrastructure (§5 line 183 + D17 inherited)", () => {
    const files = listDomainTs()
    const FORBIDDEN = [
      /from\s+["'][^"']*\/ports\b/,
      /from\s+["'][^"']*\/adapters\b/,
      /from\s+["'][^"']*\/infrastructure\b/,
      /from\s+["'][^"']*\/application\b/,
      /from\s+["']@butler\/ports\b/,
      /from\s+["']@butler\/adapters\b/,
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
      `Domain cross-package infra imports: ${violations.join(", ")}`,
    ).toEqual([])
  })
})