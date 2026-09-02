import type { Hono } from "hono"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { parseScheduleWorkerConfig } from "../schedule-config.js"
import { runScheduleTick } from "../schedule-worker.js"

/**
 * Owner control-surface routes for conversations and the schedule tick.
 * Split from owner-routes.ts (file-size gate) — behavior unchanged.
 */
export function registerConversationsScheduleRoutes(app: Hono, wiring: Wiring): void {
  app.get("/v1/owner/conversations", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const projectId = (c.req.query("projectId") ?? "").trim()
    if (!projectId) return c.text("projectId query required", 400)
    const limitRaw = Number((c.req.query("limit") ?? "50").trim())
    const limit = Number.isFinite(limitRaw) ? limitRaw : 50
    const items = await wiring.runtimeStore.listConversationsByProject({ projectId, limit })
    return c.json({ items })
  })

  app.get("/v1/owner/conversations/:conversationId/messages", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const conversationId = c.req.param("conversationId").trim()
    if (!conversationId) return c.text("conversationId required", 400)
    const limitRaw = Number((c.req.query("limit") ?? "50").trim())
    const limit = Math.min(Math.max(Number.isFinite(limitRaw) ? limitRaw : 50, 1), 200)
    const rows = await wiring.runtimeStore.listMessages(conversationId)
    const items = rows.slice(-limit).map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      createdAt: m.createdAt.toISOString(),
    }))
    return c.json({ conversationId, items })
  })

  app.post("/v1/owner/schedule/tick", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const env = process.env
    const config = parseScheduleWorkerConfig(env)
    if (!config.enabled) {
      return c.json({ ok: false, reason: "BUTLER_V5_SCHEDULE_ENABLED is not set" }, 400)
    }
    if (config.jobs.length === 0) {
      return c.json({ ok: false, reason: "no schedule jobs configured" }, 400)
    }
    const lastAttemptByJob = new Map<string, number>()
    const scheduleInFlight = { value: false }
    const stats = await runScheduleTick({
      wiring,
      jobs: config.jobs,
      nowMs: () => Date.now(),
      lastAttemptByJob,
      scheduleInFlight,
      isMainQueueBusy: () => false,
      env,
    })
    return c.json({ ok: true, stats, jobs: config.jobs.map((j) => j.id) })
  })
}
