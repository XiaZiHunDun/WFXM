import { describe, it, expect, beforeEach, afterEach } from "vitest"
import { Hono } from "hono"
import health from "./health"

const mockDbHolder = globalThis as unknown as {
  __butlerWiringDb?: { execute: (q: unknown) => Promise<unknown> }
}

describe("GET /health", () => {
  beforeEach(() => {
    mockDbHolder.__butlerWiringDb = {
      execute: async () => [{ "?column?": 1 }],
    }
  })

  afterEach(() => {
    delete mockDbHolder.__butlerWiringDb
  })

  it("returns 200 with status, version, uptime, and db check", async () => {
    const app = new Hono().route("/", health)
    const res = await app.request("/health")
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      status: string
      version: string
      uptime_seconds: number
      timestamp: string
      checks: { db: { status: string; latency_ms: number | null } }
    }
    expect(body.status).toBe("ok")
    expect(body.version).toBeDefined()
    expect(body.uptime_seconds).toBeGreaterThanOrEqual(0)
    expect(body.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/)
    expect(body.checks.db).toBeDefined()
    expect(body.checks.db.status).toBe("up")
    expect(typeof body.checks.db.latency_ms).toBe("number")
  })

  it("returns 503 when db check fails", async () => {
    mockDbHolder.__butlerWiringDb = {
      execute: async () => {
        throw new Error("db down")
      },
    }
    const app = new Hono().route("/", health)
    const res = await app.request("/health")
    expect(res.status).toBe(503)
    const body = (await res.json()) as { status: string; checks: { db: { status: string } } }
    expect(body.status).toBe("degraded")
    expect(body.checks.db.status).toBe("down")
  })

  it("GET /health/live returns 200 without deps", async () => {
    const app = new Hono().route("/", health)
    const res = await app.request("/health/live")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { status: string; timestamp: string }
    expect(body.status).toBe("ok")
    expect(body.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })
})
