import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createProjectKnowledgeStore } from "@butler/persistence"
import { makeWiring, type Wiring } from "./wiring.js"

// Stub the sync layer so each test owns its returned stats. The worker is the
// unit under test; syncProjectKnowledgeFromManifest is a dependency we don't
// want to set up an entire workspace for.
vi.mock("./project-knowledge-sync.js", async () => {
  return {
    syncProjectKnowledgeFromManifest: vi.fn(async () => ({
      scanned: 0,
      created: 0,
      updated: 0,
      skipped: 0,
      errors: [],
    })),
  }
})

import { syncProjectKnowledgeFromManifest } from "./project-knowledge-sync.js"
import {
  runProjectKnowledgeWatchTick,
  startProjectKnowledgeWatchWorkerIfEnabled,
  type ProjectKnowledgeWatchLogger,
} from "./project-knowledge-watch-worker.js"

const mockedSync = vi.mocked(syncProjectKnowledgeFromManifest)

function quietLogger(): ProjectKnowledgeWatchLogger & { infos: string[]; warns: string[]; errors: string[] } {
  const infos: string[] = []
  const warns: string[] = []
  const errors: string[] = []
  return {
    infos,
    warns,
    errors,
    info: (msg, ...args) => infos.push([msg, ...args].join(" ")),
    warn: (msg, ...args) => warns.push([msg, ...args].join(" ")),
    error: (msg, ...args) => errors.push([msg, ...args].join(" ")),
  }
}

describe("runProjectKnowledgeWatchTick", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let workDir = ""

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "pk-watch-test" })
    wiring = makeWiring({
      bridge,
      workerId: "pk-watch-test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
    })
    workDir = mkdtempSync(join(tmpdir(), "butler-pk-watch-"))
    mockedSync.mockClear()
    mockedSync.mockResolvedValue({
      scanned: 0,
      created: 0,
      updated: 0,
      skipped: 0,
      errors: [],
    })
  })

  afterEach(async () => {
    await db.close()
    if (workDir) rmSync(workDir, { recursive: true, force: true })
  })

  it("returns ok:false 'no sources manifest configured' when BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH points to a missing file", async () => {
    const result = await runProjectKnowledgeWatchTick({
      wiring,
      cwd: workDir,
      env: {
        BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH: "missing-sources.json",
      },
    })
    expect(result.ok).toBe(false)
    expect(result.reason).toMatch(/no sources manifest|no such file|cannot find/i)
    expect(mockedSync).not.toHaveBeenCalled()
  })

  it("returns ok:false reason when sources manifest JSON fails to parse", async () => {
    const manifestPath = join(workDir, "bad-sources.json")
    writeFileSync(manifestPath, "{not-json")
    const result = await runProjectKnowledgeWatchTick({
      wiring,
      cwd: workDir,
      env: {
        BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH: manifestPath,
      },
    })
    expect(result.ok).toBe(false)
    expect(result.reason).toBeDefined()
    expect(mockedSync).not.toHaveBeenCalled()
  })

  it("returns ok:true and stats when sync succeeds", async () => {
    const manifestPath = join(workDir, "good-sources.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({ version: 1, projects: { WFXM: { globs: ["**/*.md"] } } }),
    )
    mockedSync.mockResolvedValueOnce({
      scanned: 3,
      created: 1,
      updated: 0,
      skipped: 2,
      errors: [],
    })
    const logger = quietLogger()
    const result = await runProjectKnowledgeWatchTick({
      wiring,
      cwd: workDir,
      env: { BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH: manifestPath },
      logger,
    })
    expect(result.ok).toBe(true)
    expect(result.stats?.scanned).toBe(3)
    expect(result.stats?.created).toBe(1)
    expect(mockedSync).toHaveBeenCalledTimes(1)
    expect(logger.infos.some((m) => m.includes("scanned=3"))).toBe(true)
  })

  it("logs warn when sync reports errors but still returns ok:true (partial success)", async () => {
    const manifestPath = join(workDir, "good-sources.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({ version: 1, projects: { WFXM: { globs: ["**/*.md"] } } }),
    )
    mockedSync.mockResolvedValueOnce({
      scanned: 5,
      created: 2,
      updated: 1,
      skipped: 0,
      errors: ["file A unreadable", "file B parse failed"],
    })
    const logger = quietLogger()
    const result = await runProjectKnowledgeWatchTick({
      wiring,
      cwd: workDir,
      env: { BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH: manifestPath },
      logger,
    })
    expect(result.ok).toBe(true)
    expect(result.stats?.errors).toHaveLength(2)
    expect(logger.warns.some((m) => m.includes("sync errors=2"))).toBe(true)
  })
})

describe("startProjectKnowledgeWatchWorkerIfEnabled", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let workDir = ""

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "pk-watch-start-test" })
    wiring = makeWiring({
      bridge,
      workerId: "pk-watch-start-test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
    })
    workDir = mkdtempSync(join(tmpdir(), "butler-pk-watch-start-"))
    mockedSync.mockClear()
    mockedSync.mockResolvedValue({
      scanned: 0,
      created: 0,
      updated: 0,
      skipped: 0,
      errors: [],
    })
  })

  afterEach(async () => {
    await db.close()
    if (workDir) rmSync(workDir, { recursive: true, force: true })
  })

  it("returns null when env flag is not set (disabled by default)", () => {
    const handle = startProjectKnowledgeWatchWorkerIfEnabled({
      wiring,
      cwd: workDir,
      env: {},
    })
    expect(handle).toBeNull()
  })

  it("returns null when config.enabled is false even if env flag is set", () => {
    const handle = startProjectKnowledgeWatchWorkerIfEnabled({
      wiring,
      cwd: workDir,
      env: { BUTLER_V5_PROJECT_KNOWLEDGE_WATCH: "1" },
      config: { enabled: false, tickMs: 1_000, sourcesPath: null },
    })
    expect(handle).toBeNull()
  })

  it("starts a worker when enabled and ticks at the configured interval", async () => {
    const manifestPath = join(workDir, "tick-sources.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({ version: 1, projects: { WFXM: { globs: ["**/*.md"] } } }),
    )
    const logger = quietLogger()
    const handle = startProjectKnowledgeWatchWorkerIfEnabled({
      wiring,
      cwd: workDir,
      env: {
        BUTLER_V5_PROJECT_KNOWLEDGE_WATCH: "1",
        BUTLER_V5_PROJECT_KNOWLEDGE_WATCH_MS: "20",
        BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH: manifestPath,
      },
      logger,
    })
    expect(handle).not.toBeNull()
    expect(logger.infos.some((m) => m.includes("worker started"))).toBe(true)
    // Wait long enough for at least 2 ticks (initial + 1 interval).
    await new Promise((r) => setTimeout(r, 80))
    expect(mockedSync.mock.calls.length).toBeGreaterThanOrEqual(2)
    handle!.stop()
  })

  it("stop() prevents further ticks and clears timer", async () => {
    const manifestPath = join(workDir, "stop-sources.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({ version: 1, projects: { WFXM: { globs: ["**/*.md"] } } }),
    )
    const handle = startProjectKnowledgeWatchWorkerIfEnabled({
      wiring,
      cwd: workDir,
      env: {
        BUTLER_V5_PROJECT_KNOWLEDGE_WATCH: "1",
        BUTLER_V5_PROJECT_KNOWLEDGE_WATCH_MS: "10",
        BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH: manifestPath,
      },
      logger: quietLogger(),
    })
    expect(handle).not.toBeNull()
    // Let one tick run.
    await new Promise((r) => setTimeout(r, 30))
    handle!.stop()
    const callsAfterStop = mockedSync.mock.calls.length
    // Wait > tickMs and confirm no new tick happens.
    await new Promise((r) => setTimeout(r, 60))
    expect(mockedSync.mock.calls.length).toBe(callsAfterStop)
  })

  it("coalesces overlapping ticks: inFlight guard prevents concurrent runProjectKnowledgeWatchTick calls", async () => {
    // Sync that takes longer than tickMs so the next scheduled tick fires
    // while the previous one is still in-flight. The inFlight guard at line 86
    // must short-circuit the second tick to ok:false.
    let resolveSync: (() => void) | null = null
    mockedSync.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSync = () =>
            resolve({ scanned: 1, created: 0, updated: 0, skipped: 0, errors: [] })
        }),
    )
    const manifestPath = join(workDir, "coalesce-sources.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({ version: 1, projects: { WFXM: { globs: ["**/*.md"] } } }),
    )
    const handle = startProjectKnowledgeWatchWorkerIfEnabled({
      wiring,
      cwd: workDir,
      env: {
        BUTLER_V5_PROJECT_KNOWLEDGE_WATCH: "1",
        BUTLER_V5_PROJECT_KNOWLEDGE_WATCH_MS: "5",
        BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH: manifestPath,
      },
      logger: quietLogger(),
    })
    expect(handle).not.toBeNull()
    // Wait long enough for first tick to start + next tick to be scheduled.
    await new Promise((r) => setTimeout(r, 30))
    // Release first sync — only one tick should have actually entered sync.
    if (resolveSync) resolveSync()
    await new Promise((r) => setTimeout(r, 20))
    // Multiple tick calls may have been attempted but sync ran exactly once
    // (or a tiny number bounded by retry/timing) — assert it is small.
    expect(mockedSync.mock.calls.length).toBeLessThanOrEqual(2)
    handle!.stop()
  })

  it("logs error and continues ticking when sync throws", async () => {
    mockedSync.mockRejectedValueOnce(new Error("boom"))
    mockedSync.mockResolvedValue({
      scanned: 0,
      created: 0,
      updated: 0,
      skipped: 0,
      errors: [],
    })
    const manifestPath = join(workDir, "throw-sources.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({ version: 1, projects: { WFXM: { globs: ["**/*.md"] } } }),
    )
    const logger = quietLogger()
    const handle = startProjectKnowledgeWatchWorkerIfEnabled({
      wiring,
      cwd: workDir,
      env: {
        BUTLER_V5_PROJECT_KNOWLEDGE_WATCH: "1",
        BUTLER_V5_PROJECT_KNOWLEDGE_WATCH_MS: "10",
        BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH: manifestPath,
      },
      logger,
    })
    expect(handle).not.toBeNull()
    // Wait for the failing tick + at least one subsequent tick.
    await new Promise((r) => setTimeout(r, 80))
    expect(logger.errors.some((m) => m.includes("tick failed"))).toBe(true)
    expect(logger.errors.some((m) => m.includes("boom"))).toBe(true)
    expect(mockedSync.mock.calls.length).toBeGreaterThanOrEqual(2)
    handle!.stop()
  })
})
