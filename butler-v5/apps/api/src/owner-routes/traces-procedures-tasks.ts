import type { Hono } from "hono"
import { getSharedLocalTracer, resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import {
  createProcedureRecord,
  createTaskRecord,
} from "@butler/domain/knowledge/task-procedure.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { runTaskGoal } from "../task-run.js"

/**
 * Owner control-surface routes for traces, procedures and tasks.
 * Split from owner-routes.ts (file-size gate) — behavior unchanged.
 */
export function registerTracesProceduresTasksRoutes(app: Hono, wiring: Wiring): void {
  app.get("/v1/owner/traces", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const tracer = getSharedLocalTracer()
    const runId = c.req.query("runId")?.trim()
    const conversationId = c.req.query("conversationId")?.trim()
    const kindRaw = c.req.query("kind")?.trim()
    const kind =
      kindRaw === "run" ||
      kindRaw === "step" ||
      kindRaw === "capability" ||
      kindRaw === "policy" ||
      kindRaw === "grant" ||
      kindRaw === "approval"
        ? kindRaw
        : undefined
    const limitRaw = Number(c.req.query("limit") ?? 100)
    const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? Math.floor(limitRaw) : 100
    const items = tracer.list({
      ...(runId ? { runId } : {}),
      ...(conversationId ? { conversationId } : {}),
      ...(kind ? { kind } : {}),
      limit,
    })
    return c.json({
      enabled: tracer.config.enabled,
      exporter: tracer.config.exporter,
      size: tracer.size(),
      items,
    })
  })

  app.post("/v1/owner/traces/clear", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    resetSharedLocalTracer(process.env)
    return c.json({ ok: true })
  })

  app.get("/v1/owner/procedures", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.procedureStore
    if (!store) return c.json({ ok: false, reason: "procedure store unavailable" }, 503)
    return c.json({ items: await store.list(100) })
  })

  app.post("/v1/owner/procedures", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.procedureStore
    if (!store) return c.json({ ok: false, reason: "procedure store unavailable" }, 503)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly name?: string
      readonly version?: number
      readonly steps?: unknown
    }
    const created = createProcedureRecord({
      name: body.name ?? "",
      ...(typeof body.version === "number" ? { version: body.version } : {}),
      steps: Array.isArray(body.steps)
        ? body.steps.map((s) => {
            const rec = s as Record<string, unknown>
            return {
              key: String(rec["key"] ?? ""),
              title: String(rec["title"] ?? ""),
              goal: String(rec["goal"] ?? ""),
              ...(typeof rec["when"] === "string" ? { when: rec["when"] } : {}),
            }
          })
        : [],
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    const saved = await store.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.get("/v1/owner/tasks", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.taskStore
    if (!store) return c.json({ ok: false, reason: "task store unavailable" }, 503)
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const statusRaw = (c.req.query("status") ?? "").trim()
    const status =
      statusRaw === "open" || statusRaw === "done" || statusRaw === "cancelled"
        ? statusRaw
        : undefined
    const items = await store.listBySubject({
      subject,
      ...(status ? { status } : {}),
      limit: 100,
    })
    return c.json({ items })
  })

  app.post("/v1/owner/tasks", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.taskStore
    if (!store) return c.json({ ok: false, reason: "task store unavailable" }, 503)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
      readonly title?: string
      readonly goal?: string
      readonly conversationId?: string
      readonly procedureId?: string
      readonly procedureStepIndex?: number
    }
    const created = createTaskRecord({
      subject: body.subject ?? "owner",
      title: body.title ?? "",
      goal: body.goal ?? "",
      ...(typeof body.conversationId === "string"
        ? { conversationId: body.conversationId }
        : {}),
      ...(typeof body.procedureId === "string" ? { procedureId: body.procedureId } : {}),
      ...(typeof body.procedureStepIndex === "number"
        ? { procedureStepIndex: body.procedureStepIndex }
        : {}),
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    const saved = await store.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.post("/v1/owner/tasks/:taskId/run", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const taskId = c.req.param("taskId")
    const body = (await c.req.json().catch(() => ({}))) as { readonly advance?: boolean }
    try {
      const result = await runTaskGoal({
        wiring,
        taskId,
        ...(body.advance === false ? { advance: false } : {}),
      })
      return c.json({
        ok: true,
        task: result.task,
        goal: result.goal,
        stepKey: result.stepKey,
        reply: result.loop.reply,
        finalDecision: result.loop.finalDecision,
      })
    } catch (err) {
      return c.json(
        { ok: false, reason: err instanceof Error ? err.message : String(err) },
        400,
      )
    }
  })

  app.post("/v1/owner/tasks/:taskId/done", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.taskStore
    if (!store) return c.json({ ok: false, reason: "task store unavailable" }, 503)
    const existing = await store.get(c.req.param("taskId"))
    if (!existing) return c.json({ ok: false, reason: "not found" }, 404)
    const updated = await store.update({
      ...existing,
      status: "done",
      updatedAt: Date.now(),
    })
    return c.json({ ok: true, item: updated })
  })
}
