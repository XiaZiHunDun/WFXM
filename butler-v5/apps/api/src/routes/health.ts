/**
 * D77 T5 (DEPLOY-HEALTH): GET /health endpoint.
 *
 * Combined liveness + readiness probe for Docker HEALTHCHECK, K8s probes,
 * and load-balancer health checks. No auth — probes run from the same
 * network namespace as the butler container (OS-level network defense).
 *
 * Endpoints:
 *   GET /health      — readiness: db check + version + uptime
 *   GET /health/live — liveness: no dependencies, fast path for k8s/Docker
 *
 * Response shape (200 when healthy, 503 when degraded):
 *   { status, version, uptime_seconds, timestamp, checks: { db: { status, latency_ms } } }
 */
import { Hono } from "hono"
import { sql } from "drizzle-orm"
import type { Wiring } from "../wiring.js"

/** Minimal interface for the DB connectivity check. */
interface HealthcheckDb {
  execute(query: unknown): Promise<unknown>
}

const startTime = Date.now()
const VERSION = process.env["npm_package_version"] ?? "unknown"

/**
 * Resolve the DB client used for the readiness probe.
 *
 * Production: wired from `wiring.db` at register time.
 * Tests: injected via `globalThis.__butlerWiringDb` to avoid coupling
 * the unit test to the full bootstrap-wiring lifecycle.
 */
function resolveDb(wiring: Wiring | null): HealthcheckDb | null {
  if (wiring) return wiring.db as unknown as HealthcheckDb
  const mock = (globalThis as { __butlerWiringDb?: HealthcheckDb }).__butlerWiringDb
  return mock ?? null
}

/**
 * Register /health endpoints on the Hono app. D77 T5: same register*
 * pattern as the other routes in `apps/api/src/routes/*`.
 *
 * If `wiring` is null, falls back to the `globalThis.__butlerWiringDb`
 * mock so unit tests can exercise the handler without bootstrap-wiring.
 */
export function registerHealthRoutes(app: Hono, wiring: Wiring | null): void {
  app.get("/health", async (c) => {
    const uptime_seconds = Math.floor((Date.now() - startTime) / 1000)
    // Resolve per-request so unit tests can swap the mock between cases.
    const db = resolveDb(wiring)

    let db_status: "up" | "down" = "down"
    let db_latency_ms: number | null = null
    if (db) {
      try {
        const t0 = Date.now()
        await db.execute(sql`SELECT 1`)
        db_latency_ms = Date.now() - t0
        db_status = "up"
      } catch (err) {
        // eslint-disable-next-line no-console -- operator log when no logger injected
        console.error("[health] db check failed:", err)
      }
    }

    const healthy = db_status === "up"
    const body = {
      status: healthy ? "ok" : "degraded",
      version: VERSION,
      uptime_seconds,
      timestamp: new Date().toISOString(),
      checks: {
        db: {
          status: db_status,
          latency_ms: db_latency_ms,
        },
      },
    }

    return c.json(body, healthy ? 200 : 503)
  })

  app.get("/health/live", (c) =>
    c.json({ status: "ok", timestamp: new Date().toISOString() }),
  )
}

/**
 * Standalone Hono sub-app for unit tests. Mirrors the production
 * route shape so tests can mount it with `new Hono().route("/", health)`.
 */
const health = new Hono()
registerHealthRoutes(health, null)
export default health
