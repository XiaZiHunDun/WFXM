/**
 * Arch guard (D46 Repository Port): lock the Repository Port seam.
 *
 * Materialization (方式 A：先造触发条件再物化):
 *   - second-persistence-impl trigger: `packages/persistence/src/memory/
 *     runtime-store.ts` (`createInMemoryRuntimeStore`) sits beside the
 *     production `packages/persistence/src/runtime-store.ts`
 *     (`createRuntimeStore`, Drizzle/postgres). Both implement the same
 *     `RuntimeStore` contract → it is a real replaceable seam.
 *   - `packages/ports/src/core/repository.ts` materializes the seam as the
 *     Repository Port under DESIGN §7, reusing the domain `RuntimeStore`
 *     contract (single source of truth; no duplicated interface).
 *
 * Static checks (no runtime):
 *   - repository.ts exists, exports `RepositoryPort`/`RuntimeStore`.
 *   - repository.ts is interface-only: 0 fetch / 0 db / 0 IO.
 *   - dependency-inward: repository.ts imports `@butler/domain` (allowed,
 *     precedent: event-store.ts imports domain ActorRef) but NOT
 *     `@butler/persistence` / `@butler/runtime` / `@butler/adapters`.
 *   - both Repository adapters exist under packages/persistence.
 *
 * Runtime behavior is verified by:
 *   - packages/persistence/src/memory/runtime-store.test.ts
 */
import { describe, expect, it } from "vitest"
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"

const REPO = join(__dirname, "../../")
const PORTS_PKG = join(REPO, "packages")
const REPOSITORY = join(PORTS_PKG, "ports/src/core/repository.ts")
const PROD_STORE = join(PORTS_PKG, "persistence/src/runtime-store.ts")
const MEM_STORE = join(PORTS_PKG, "persistence/src/memory/runtime-store.ts")

describe("arch: Repository Port (D46 — second persistence impl trigger)", () => {
  it("ports/core/repository.ts exists and exports RepositoryPort, and is pure (0 fetch / 0 db / 0 IO)", () => {
    expect(existsSync(REPOSITORY)).toBe(true)
    const src = readFileSync(REPOSITORY, "utf-8")
    expect(src).toMatch(/export\s+type\s+RepositoryPort\b/)
    expect(src).toMatch(/export\s+type\s*\{[^}]*RuntimeStore/)
    // Port is pure: no IO / DB / adapters protocol surface.
    expect(src).not.toMatch(/\bfetch\s*\(|pgTable\s*\(|drizzle|node:fs|new\s+(Pool|Client)\b/)
  })

  it("repository.ts depends inward (imports @butler/domain, never persistence/runtime/adapters)", () => {
    const src = readFileSync(REPOSITORY, "utf-8")
    expect(src).toMatch(/from\s+["']@butler\/domain\//)
    expect(src).not.toMatch(
      /from\s+["'](?:@butler\/(?:persistence|runtime|adapters)|[^"']*packages\/(?:persistence|runtime|adapters))/,
    )
  })

  it("both Repository adapters exist (postgres + in-memory) — the replaceability seam", () => {
    expect(existsSync(PROD_STORE)).toBe(true)
    expect(existsSync(MEM_STORE)).toBe(true)
    const memSrc = readFileSync(MEM_STORE, "utf-8")
    expect(memSrc).toMatch(/export\s+function\s+createInMemoryRuntimeStore/)
  })
})