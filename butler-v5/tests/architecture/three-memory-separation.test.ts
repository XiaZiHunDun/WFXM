/**
 * Arch guard (D9-arch-align §20 #9): Transcript, Durable Memory and
 * Project Knowledge 不互相冒充。
 *
 * DESIGN §12 + §20 #9: three memory layers with distinct tables, domain
 * modules, and persistence stores. Cross-imports would mean one layer
 * starts impersonating another (e.g. durable-memory code reaching into
 * project-knowledge types, or transcript storage writing to memory tables).
 *
 * Static checks (no runtime):
 *   - `durable-memory-store.ts` does NOT import from project-knowledge paths
 *   - `project-knowledge-store.ts` does NOT import from durable-memory paths
 *   - `runtime-store.ts` (transcript home) does NOT import from any memory store
 *   - Domain module `durable-memory.ts` does NOT import project-knowledge domain
 *   - Domain module `project-knowledge.ts` does NOT import durable-memory domain
 *   - Schema declares three distinct tables (already enforced by migration
 *     tests; double-checked here so the invariant survives any future
 *     schema refactor)
 *
 * Runtime behavior is verified by:
 *   - packages/persistence/src/durable-memory-store.test.ts (candidate /
 *     confirmed / rejected / expiry semantics)
 *   - packages/persistence/src/project-knowledge-store.test.ts (CRUD +
 *     project isolation)
 *   - packages/persistence/src/runtime-store.test.ts (transcript
 *     redaction + working-set history)
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const DURABLE_MEMORY_STORE = join(
  __dirname,
  "../../packages/persistence/src/durable-memory-store.ts",
)
const PROJECT_KNOWLEDGE_STORE = join(
  __dirname,
  "../../packages/persistence/src/project-knowledge-store.ts",
)
const RUNTIME_STORE = join(
  __dirname,
  "../../packages/persistence/src/runtime-store.ts",
)
const DURABLE_MEMORY_DOMAIN = join(
  __dirname,
  "../../packages/domain/src/knowledge/durable-memory.ts",
)
const PROJECT_KNOWLEDGE_DOMAIN = join(
  __dirname,
  "../../packages/domain/src/knowledge/project-knowledge.ts",
)
const SCHEMA = join(
  __dirname,
  "../../packages/persistence/src/schema.ts",
)

function importsFrom(src: string, regex: RegExp): readonly string[] {
  return src.match(regex) ?? []
}

describe("arch: three memory separation (§20 #9)", () => {
  it("durable-memory-store does NOT import project-knowledge paths", () => {
    const src = readFileSync(DURABLE_MEMORY_STORE, "utf-8")
    const hits = importsFrom(src, /from\s+["'][^"']*project-knowledge[^"']*["']/g)
    expect(hits, `unexpected project-knowledge imports: ${hits.join(", ")}`).toEqual([])
  })

  it("project-knowledge-store does NOT import durable-memory paths", () => {
    const src = readFileSync(PROJECT_KNOWLEDGE_STORE, "utf-8")
    const hits = importsFrom(src, /from\s+["'][^"']*durable-memory[^"']*["']/g)
    expect(hits, `unexpected durable-memory imports: ${hits.join(", ")}`).toEqual([])
  })

  it("runtime-store (transcript) does NOT import any memory store", () => {
    const src = readFileSync(RUNTIME_STORE, "utf-8")
    const hits = importsFrom(
      src,
      /from\s+["'][^"']*(durable-memory-store|project-knowledge-store)[^"']*["']/g,
    )
    expect(hits, `unexpected memory-store imports: ${hits.join(", ")}`).toEqual([])
  })

  it("durable-memory domain does NOT import project-knowledge domain", () => {
    const src = readFileSync(DURABLE_MEMORY_DOMAIN, "utf-8")
    const hits = importsFrom(src, /from\s+["'][^"']*project-knowledge[^"']*["']/g)
    expect(hits, `unexpected project-knowledge imports: ${hits.join(", ")}`).toEqual([])
  })

  it("project-knowledge domain does NOT import durable-memory domain", () => {
    const src = readFileSync(PROJECT_KNOWLEDGE_DOMAIN, "utf-8")
    const hits = importsFrom(src, /from\s+["'][^"']*durable-memory[^"']*["']/g)
    expect(hits, `unexpected durable-memory imports: ${hits.join(", ")}`).toEqual([])
  })

  it("schema declares three distinct memory tables", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    // The persistence schema must declare the three memory tables
    // (transcript is split across messages / conversations / runs / steps /
    // auditEvents / scopedGrants — checked separately; here we focus on the
    // two dedicated knowledge tables).
    expect(src).toMatch(/export const messages\s*=\s*pgTable/)
    expect(src).toMatch(/export const durableMemories\s*=\s*pgTable/)
    expect(src).toMatch(/export const projectKnowledgeItems\s*=\s*pgTable/)
  })
})