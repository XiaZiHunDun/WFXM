import type { Hono } from "hono"
import { getSharedLocalTracer, resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import {
  createProcedureRecord,
  createTaskRecord,
} from "@butler/domain/knowledge/task-procedure.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { handleTaskRun } from "./tasks-run.js"
import { unauthorizedForOwner } from "../owner-jargon.js"

/**
 * Owner control-surface routes for traces, procedures and tasks.
 * Split from owner-routes.ts (file-size gate) — behavior unchanged.
 */
export function registerTracesProceduresTasksRoutes(app: Hono, wiring: Wiring): void {
  app.get("/v1/owner/traces", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
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
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    resetSharedLocalTracer(process.env)
    return c.json({ ok: true })
  })

  app.get("/v1/owner/procedures", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const store = wiring.procedureStore
    if (!store) return c.json({ ok: false, reason: "流程存储暂不可用" }, 503)
    return c.json({ items: await store.list(100) })
  })

  app.post("/v1/owner/procedures", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
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
    // D59 T1 (audit #1 F-26 procedures): §13 audit completeness.
    // D63 T1 (audit #9 F-11): runtimeStore?. optional chaining silently
    // skipped audit emit when store was undefined. Mirror D62 T1 F-12
    // pattern (memories.ts:137-154) — non-optional with try/catch so a
    // failed audit write logs to stderr instead of vanishing.
    try {
      await wiring.runtimeStore.appendAuditEvent({
        auditId: crypto.randomUUID(),
        runId: null,
        conversationId: null,
        // D66 T1b-apps-api: thread request-scoped correlation. Owner
        // direct API call; no inbound run — pass null.
        correlationId: null,
        action: "procedure.created",
        subject: "owner",
        detail: { procedureId: saved.id, name: saved.name },
        createdAt: new Date(),
      })
    } catch (err) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error("[traces-procedures-tasks] appendAuditEvent (procedure.created) failed:", err)
    }
    return c.json({ ok: true, item: saved })
  })

  app.get("/v1/owner/tasks", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
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
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
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
    // D59 T1 (audit #1 F-26 task): §13 audit completeness.
    // D63 T1 (audit #9 F-11): mirror D62 T1 F-12 pattern (memories.ts:137-154)
    // — non-optional with try/catch so a failed audit write logs to stderr
    // instead of silently skipping when runtimeStore is undefined.
    try {
      await wiring.runtimeStore.appendAuditEvent({
        auditId: crypto.randomUUID(),
        runId: null,
        conversationId: null,
        // D66 T1b-apps-api: thread request-scoped correlation. Owner
        // direct API call; no inbound run — pass null.
        correlationId: null,
        action: "task.created",
        subject: body.subject ?? "owner",
        detail: { taskId: saved.id, title: saved.title },
        createdAt: new Date(),
      })
    } catch (err) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error("[traces-procedures-tasks] appendAuditEvent (task.created) failed:", err)
    }
    return c.json({ ok: true, item: saved })
  })

  app.post("/v1/owner/tasks/:taskId/run", (c) => handleTaskRun(c, wiring))

  app.post("/v1/owner/tasks/:taskId/done", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const store = wiring.taskStore
    if (!store) return c.json({ ok: false, reason: "task store unavailable" }, 503)
    const existing = await store.get(c.req.param("taskId"))
    if (!existing) return c.json({ ok: false, reason: "未找到对应记录" }, 404)
    const updated = await store.update({
      ...existing,
      status: "done",
      updatedAt: Date.now(),
    })
    // D59 T1 (audit #1 F-27): §13 audit completeness — task status
    // transition writes audit_event.
    // D63 T1 (audit #9 F-11): mirror D62 T1 F-12 pattern (memories.ts:137-154)
    // — non-optional with try/catch so a failed audit write logs to stderr
    // instead of silently skipping when runtimeStore is undefined.
    try {
      await wiring.runtimeStore.appendAuditEvent({
        auditId: crypto.randomUUID(),
        runId: null,
        conversationId: null,
        // D66 T1b-apps-api: thread request-scoped correlation. Owner
        // direct API call; no inbound run — pass null.
        correlationId: null,
        action: "task.done",
        subject: existing.subject,
        detail: { taskId: existing.id, fromStatus: existing.status },
        createdAt: new Date(),
      })
    } catch (err) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error("[traces-procedures-tasks] appendAuditEvent (task.done) failed:", err)
    }
    return c.json({ ok: true, item: updated })
  })
}
