import { describe, expect, it } from "vitest"
import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { appendEvents, loadStream } from "./event-store.js"
import { openButlerDatabase } from "./db-open.js"

function testPostgresUrl(env: NodeJS.ProcessEnv): string {
  const override = (env["BUTLER_V5_TEST_DATABASE_URL"] ?? "").trim()
  if (override) return override
  if ((env["CI"] ?? "").trim()) {
    return "postgres://test:test@127.0.0.1:5432/butler_test"
  }
  return "postgres://butler:butler_dev@127.0.0.1:5432/butler_v5"
}

/**
 * The postgres round-trip test needs a real postgres server, which is not present
 * in every sandbox/CI worker. Probe once at collection time and skip cleanly when
 * unreachable — the "open → write → close → reopen → read" survival semantics are
 * already covered DB-less by the pglite file-path test below, so this guard is
 * test-infra only (no production behavior change).
 */
async function probePostgres(env: NodeJS.ProcessEnv): Promise<boolean> {
  try {
    const probe = await openButlerDatabase({
      BUTLER_V5_DB: "postgres",
      DATABASE_URL: testPostgresUrl(env),
    })
    if (probe.ok) await probe.value.close()
    return probe.ok
  } catch {
    return false
  }
}

const postgresRoundTrip = (await probePostgres(process.env)) ? it : it.skip

describe("openButlerDatabase", () => {
  it("opens pglite and applies schema", async () => {
    const opened = await openButlerDatabase({ BUTLER_V5_DB: "pglite", VITEST: "true", NODE_ENV: "test" })
    expect(opened.ok).toBe(true)
    if (!opened.ok) return
    expect(opened.value.kind).toBe("pglite")
    const streamId = `pglite-${crypto.randomUUID()}`
    await appendEvents(
      opened.value.db,
      streamId,
      { t: 1 },
      {
        eventId: "e1",
        eventType: "Test",
        eventVersion: 1,
        correlationId: "c1",
        occurredAt: new Date(),
        actor: { kind: "system", id: "test" },
      },
    )
    const rows = await loadStream(opened.value.db, streamId)
    expect(rows).toHaveLength(1)
    await opened.value.close()
  })

  it("refuses postgres without DATABASE_URL", async () => {
    const opened = await openButlerDatabase({ BUTLER_V5_DB: "postgres" })
    expect(opened.ok).toBe(false)
    if (opened.ok) return
    expect(opened.reason).toMatch(/DATABASE_URL/)
  })

  postgresRoundTrip("postgres append survives reconnect", async () => {
    const url = testPostgresUrl(process.env)
    const streamId = `persist-roundtrip-${crypto.randomUUID()}`
    const first = await openButlerDatabase({
      BUTLER_V5_DB: "postgres",
      DATABASE_URL: url,
    })
    expect(first.ok).toBe(true)
    if (!first.ok) {
      throw new Error(`expected postgres at ${url.replace(/:[^:@/]+@/, ":***@")}: ${first.reason}`)
    }
    await appendEvents(
      first.value.db,
      streamId,
      { n: 1 },
      {
        eventId: crypto.randomUUID(),
        eventType: "PersistProbe",
        eventVersion: 1,
        correlationId: "roundtrip",
        occurredAt: new Date(),
        actor: { kind: "system", id: "test" },
      },
    )
    await first.value.close()

    const second = await openButlerDatabase({
      BUTLER_V5_DB: "postgres",
      DATABASE_URL: url,
    })
    expect(second.ok).toBe(true)
    if (!second.ok) return
    const rows = await loadStream(second.value.db, streamId)
    expect(rows).toHaveLength(1)
    expect(rows[0]?.eventType).toBe("PersistProbe")
    await second.value.close()
  })

  it("pglite file path survives reconnect", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "pglite-persist-"))
    const streamId = `pglite-file-${crypto.randomUUID()}`
    try {
      const first = await openButlerDatabase({
        BUTLER_V5_DB: "pglite",
        BUTLER_V5_PGLITE_DATA_DIR: tmp,
        NODE_ENV: "development",
      })
      expect(first.ok).toBe(true)
      if (!first.ok) return
      await appendEvents(
        first.value.db,
        streamId,
        { n: 1 },
        {
          eventId: crypto.randomUUID(),
          eventType: "PersistProbe",
          eventVersion: 1,
          correlationId: "pglite-file",
          occurredAt: new Date(),
          actor: { kind: "system", id: "test" },
        },
      )
      await first.value.close()

      const second = await openButlerDatabase({
        BUTLER_V5_DB: "pglite",
        BUTLER_V5_PGLITE_DATA_DIR: tmp,
        NODE_ENV: "development",
      })
      expect(second.ok).toBe(true)
      if (!second.ok) return
      const rows = await loadStream(second.value.db, streamId)
      expect(rows).toHaveLength(1)
      await second.value.close()
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })
})
