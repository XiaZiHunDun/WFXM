import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { parseProjectKnowledgeSourcesJson } from "@butler/domain/knowledge/project-knowledge-sources.js"
import { createDocumentStore, createProjectKnowledgeStore } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring } from "./wiring.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createRuntimeStore } from "@butler/persistence"
import { syncProjectKnowledgeFromManifest } from "./project-knowledge-sync.js"

describe("project-knowledge-sync", () => {
  it("syncs text file snapshots from manifest globs", async () => {
    const root = mkdtempSync(join(tmpdir(), "pk-sync-"))
    mkdirSync(join(root, "docs"), { recursive: true })
    writeFileSync(join(root, "docs/decision.md"), "# MCP\nUse manifest for multi-server.")

    const parsed = parseProjectKnowledgeSourcesJson(
      JSON.stringify({ version: 1, projects: { WFXM: { globs: ["docs/decision.md"] } } }),
    )
    if (!parsed.ok) throw new Error(parsed.reason)

    const db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-pk-sync" })
    const runtimeStore = createRuntimeStore(db.db)
    const wiring = makeWiring({
      bridge,
      workerId: "w-pk-sync",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
      documentStore: createDocumentStore(db.db),
    })

    const stats = await syncProjectKnowledgeFromManifest({
      wiring,
      manifest: parsed.manifest,
      env: { BUTLER_V5_WORKSPACE_ROOT: root },
      nowMs: () => 5000,
    })
    expect(stats.scanned).toBe(1)
    expect(stats.created).toBe(1)
    expect(stats.errors).toHaveLength(0)

    const store = wiring.projectKnowledgeStore
    if (!store) throw new Error("projectKnowledgeStore missing")
    const listed = await store.listByProject({ projectId: "WFXM" })
    expect(listed.some((i) => i.provenance.sourcePath === "docs/decision.md")).toBe(true)

    const stats2 = await syncProjectKnowledgeFromManifest({
      wiring,
      manifest: parsed.manifest,
      env: { BUTLER_V5_WORKSPACE_ROOT: root },
      nowMs: () => 5000,
    })
    expect(stats2.skipped).toBe(1)

    await db.close()
    rmSync(root, { recursive: true, force: true })
  })

  it("syncs PDF paths via markitdown chain into ingested_document", async () => {
    const root = mkdtempSync(join(tmpdir(), "pk-sync-md-"))
    mkdirSync(join(root, "docs"), { recursive: true })
    writeFileSync(join(root, "docs/spec.pdf"), "%PDF-1.4 fixture")

    const parsed = parseProjectKnowledgeSourcesJson(
      JSON.stringify({
        version: 1,
        projects: { WFXM: { globs: [], markitdownGlobs: ["docs/*.pdf"] } },
      }),
    )
    if (!parsed.ok) throw new Error(parsed.reason)

    const db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-pk-md" })
    const runtimeStore = createRuntimeStore(db.db)
    const wiring = makeWiring({
      bridge,
      workerId: "w-pk-md",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
      documentStore: createDocumentStore(db.db),
      mcp: {
        runtimeTools: [
          {
            name: "mcp_markitdown_convert_to_markdown",
            risk: "low",
            async run() {
              return { ok: true, output: "# Spec\nConverted from PDF fixture." }
            },
          },
        ],
        llmTools: [],
        mode: "multi",
        discovered: [],
        servers: [],
        serverIdByCapability: {},
      },
    })

    const stats = await syncProjectKnowledgeFromManifest({
      wiring,
      manifest: parsed.manifest,
      env: { BUTLER_V5_WORKSPACE_ROOT: root },
      nowMs: () => 9000,
    })
    expect(stats.scanned).toBe(1)
    expect(stats.created).toBe(1)
    expect(stats.errors).toHaveLength(0)

    const store = wiring.projectKnowledgeStore
    if (!store) throw new Error("projectKnowledgeStore missing")
    const item = await store.findBySourcePath({
      projectId: "WFXM",
      sourcePath: "docs/spec.pdf",
    })
    expect(item?.kind).toBe("ingested_document")
    expect(item?.body).toContain("Converted from PDF")

    await db.close()
    rmSync(root, { recursive: true, force: true })
  })
})
