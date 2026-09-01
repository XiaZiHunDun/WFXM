import type { Hono } from "hono"
import {
  approveWaitingStep,
  denyWaitingStep,
  parsePendingCapabilityInput,
} from "@butler/runtime/approval-runtime.js"
import { cancelRunCascade, expireOverdueRuns } from "@butler/runtime/run-lifecycle.js"
import {
  confirmDurableMemory,
  createDurableMemoryRecord,
  rejectDurableMemory,
  type DurableMemoryStatus,
} from "@butler/domain/knowledge/durable-memory.js"
import {
  ingestDocumentRecord,
  parseDocumentFormat,
} from "@butler/domain/knowledge/document-ingest.js"
import {
  createProjectKnowledgeRecord,
  projectKnowledgeFromDocument,
  type ProjectKnowledgeKind,
} from "@butler/domain/knowledge/project-knowledge.js"
import {
  createProcedureRecord,
  createTaskRecord,
} from "@butler/domain/knowledge/task-procedure.js"
import { getSharedLocalTracer, resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { resumeApprovedCapability } from "./approval-resume.js"
import { runTaskGoal } from "./task-run.js"
import {
  assertOwnerApprovalRunTrigger,
  buildOwnerApprovalRunTrigger,
} from "./owner-approval-trigger.js"
import type { Wiring } from "./wiring.js"
import { ownerAuthorized } from "./owner-auth.js"
import { parseScheduleWorkerConfig } from "./schedule-config.js"
import { runScheduleTick } from "./schedule-worker.js"
import { revokeScopedGrantsForMcpServer } from "@butler/runtime/mcp-grant-lifecycle.js"
import { mcpServerIdFromEnv } from "@butler/runtime/mcp-consent.js"
import { isMcpEnabled } from "@butler/runtime/mcp-gate.js"
import { defaultMcpProviderMetadata, mcpProviderMetadataFromManifest } from "@butler/domain/governance/mcp-tool-capability.js"
import { loadMcpManifestFromEnv, resolveMcpManifestServer } from "./mcp-manifest.js"
import { readFileSync } from "node:fs"
import { resolveUnderWorkspace, workspaceRootFrom } from "./workspace-tools.js"
import {
  loadProjectKnowledgeSourcesFromEnv,
  isProjectKnowledgeWatchEnabled,
} from "./project-knowledge-sources-config.js"
import { syncProjectKnowledgeFromManifest } from "./project-knowledge-sync.js"

export function createOwnerRoutes(app: Hono, wiring: Wiring): void {
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

  app.get("/v1/owner/approvals", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const rows = await wiring.runtimeStore.listWaitingApprovalSteps()
    // P1 acceptance: sensitive parameters are not surfaced to the Owner-facing
    // approvals list. The pending tool `args` are needed only for resume and stay
    // inside the Step; the list exposes capability/resource/question/digest etc.
    const items = rows.map((step) => {
      const base = { id: step.id, runId: step.runId, status: step.status, createdAt: step.createdAt }
      const pending = parsePendingCapabilityInput(step.input)
      if (!pending) return base
      return {
        ...base,
        capability: pending.capability,
        resource: pending.resource,
        question: pending.question,
        expiresAtMs: pending.expiresAtMs,
        subject: pending.subject,
        digest: pending.digest,
        kind: pending.kind,
        risk: pending.risk,
        ...(pending.wechatUserId ? { wechatUserId: pending.wechatUserId } : {}),
      }
    })
    return c.json({ items })
  })

  app.post("/v1/owner/approvals/:stepId/approve", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const stepId = c.req.param("stepId")
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
      readonly elevateNetwork?: boolean
      readonly sandboxProfile?: string
      readonly networkAllowlist?: readonly string[]
    }
    try {
      const decision = await approveWaitingStep(
        wiring.runtimeStore,
        stepId,
        body.subject ?? "owner",
        {
          ...(body.elevateNetwork === true ? { elevateNetwork: true } : {}),
          ...(typeof body.sandboxProfile === "string"
            ? { sandboxProfile: body.sandboxProfile }
            : {}),
          ...(Array.isArray(body.networkAllowlist) && body.networkAllowlist.length > 0
            ? { networkAllowlist: body.networkAllowlist }
            : {}),
        },
      )
      const pending = parsePendingCapabilityInput(decision.step.input)
      if (!pending) {
        return c.json({ ok: false, reason: "invalid pending capability step" }, 400)
      }
      if (decision._tag === "alreadyProcessed") {
        return c.json({ ok: true, stepId, alreadyProcessed: true, reason: decision.reason })
      }
      const ownerSubject = body.subject ?? "owner"
      const trigger = buildOwnerApprovalRunTrigger({
        subject: ownerSubject,
        conversationId: pending.conversationId,
        stepId,
        capability: pending.capability,
      })
      const triggerCheck = assertOwnerApprovalRunTrigger(trigger)
      if (!triggerCheck.ok) {
        return c.json({ ok: false, reason: triggerCheck.reason }, 400)
      }
      const resumed = await resumeApprovedCapability(wiring, decision, { trigger })
      return c.json({
        ok: resumed.ok,
        stepId,
        grant: {
          id: decision.grant.id,
          sandboxProfile: decision.grant.sandboxProfile,
          networkAllowlist: decision.grant.networkAllowlist,
          ...(decision.grant.scope.mcp ? { mcp: decision.grant.scope.mcp } : {}),
        },
        trigger: {
          source: trigger.source,
          idempotencyKey: trigger.idempotencyKey,
        },
        output: resumed.ok ? resumed.output : undefined,
        reason: resumed.ok ? undefined : resumed.reason,
      })
    } catch (err) {
      return c.json(
        {
          ok: false,
          reason: err instanceof Error ? err.message : String(err),
        },
        400,
      )
    }
  })

  app.post("/v1/owner/approvals/:stepId/deny", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const stepId = c.req.param("stepId")
    try {
      const deny = await denyWaitingStep(wiring.runtimeStore, stepId, "owner")
      return c.json({ ok: true, stepId, ...(deny.alreadyProcessed ? { alreadyProcessed: true } : {}) })
    } catch (err) {
      return c.json(
        {
          ok: false,
          reason: err instanceof Error ? err.message : String(err),
        },
        400,
      )
    }
  })

  app.post("/v1/owner/runs/:runId/cancel", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const runId = c.req.param("runId")
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
      readonly reason?: string
    }
    try {
      // D4-arch-align §20 #7: cancel cascades to all descendants so revoked
      // safety actions actually propagate (children do not outlive parent).
      const cancelled = await cancelRunCascade(wiring.runtimeStore, runId, {
        subject: body.subject ?? "owner",
        ...(body.reason ? { reason: body.reason } : {}),
      })
      const head = cancelled[cancelled.length - 1]
      if (!head) {
        return c.json({ ok: false, reason: "run not found" }, 404)
      }
      return c.json({
        ok: true,
        runId: head.id,
        status: head.status,
        version: head.version,
        cascadedCount: Math.max(cancelled.length - 1, 0),
      })
    } catch (err) {
      return c.json(
        {
          ok: false,
          reason: err instanceof Error ? err.message : String(err),
        },
        400,
      )
    }
  })

  app.post("/v1/owner/runs/expire-overdue", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
    }
    try {
      const expired = await expireOverdueRuns(wiring.runtimeStore, {
        subject: body.subject ?? "owner",
      })
      return c.json({
        ok: true,
        count: expired.length,
        runIds: expired.map((r) => r.id),
      })
    } catch (err) {
      return c.json(
        {
          ok: false,
          reason: err instanceof Error ? err.message : String(err),
        },
        400,
      )
    }
  })

  app.get("/v1/owner/memories", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const statusRaw = (c.req.query("status") ?? "").trim()
    const status: DurableMemoryStatus | undefined =
      statusRaw === "candidate" || statusRaw === "confirmed" || statusRaw === "rejected"
        ? statusRaw
        : undefined
    if (statusRaw && !status) {
      return c.json({ ok: false, reason: "invalid status (must be candidate|confirmed|rejected)" }, 400)
    }
    const limitRaw = c.req.query("limit")
    const limit = limitRaw ? Number.parseInt(limitRaw, 10) : 20
    if (!Number.isFinite(limit) || limit < 1 || limit > 100) {
      return c.json({ ok: false, reason: "invalid limit (1-100, default 20)" }, 400)
    }
    const offsetRaw = c.req.query("offset")
    const offset = offsetRaw ? Number.parseInt(offsetRaw, 10) : 0
    if (!Number.isFinite(offset) || offset < 0) {
      return c.json({ ok: false, reason: "invalid offset (>=0, default 0)" }, 400)
    }

    const items = await store.listBySubject({
      subject,
      ...(status ? { status } : {}),
      limit,
      offset,
    })
    const total = await store.countBySubject({
      subject,
      ...(status ? { status } : {}),
    })
    return c.json({
      items,
      total,
      hasMore: offset + items.length < total,
    })
  })

  app.post("/v1/owner/memories", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
      readonly content?: string
      readonly sourceKind?: string
      readonly status?: string
      readonly confidence?: number
      readonly provenance?: Record<string, unknown>
      readonly expiresAt?: number | null
    }
    const sourceKind =
      body.sourceKind === "message" || body.sourceKind === "document" ? body.sourceKind : "owner"
    const created = createDurableMemoryRecord({
      subject: body.subject ?? "owner",
      content: body.content ?? "",
      sourceKind,
      ...(body.status === "candidate" || body.status === "confirmed" || body.status === "rejected"
        ? { status: body.status }
        : {}),
      ...(typeof body.confidence === "number" ? { confidence: body.confidence } : {}),
      ...(body.provenance
        ? {
            provenance: {
              ...(typeof body.provenance["conversationId"] === "string"
                ? { conversationId: body.provenance["conversationId"] }
                : {}),
              ...(typeof body.provenance["messageId"] === "string"
                ? { messageId: body.provenance["messageId"] }
                : {}),
              ...(typeof body.provenance["documentId"] === "string"
                ? { documentId: body.provenance["documentId"] }
                : {}),
              ...(typeof body.provenance["note"] === "string"
                ? { note: body.provenance["note"] }
                : {}),
            },
          }
        : {}),
      ...(body.expiresAt !== undefined ? { expiresAt: body.expiresAt } : {}),
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    const saved = await store.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.post("/v1/owner/memories/:memoryId/confirm", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const memoryId = c.req.param("memoryId")
    const existing = await store.get(memoryId)
    if (!existing) return c.json({ ok: false, reason: "not found" }, 404)
    const updated = await store.update(confirmDurableMemory(existing, Date.now()))
    return c.json({ ok: true, item: updated })
  })

  app.post("/v1/owner/memories/:memoryId/reject", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const memoryId = c.req.param("memoryId")
    const existing = await store.get(memoryId)
    if (!existing) return c.json({ ok: false, reason: "not found" }, 404)
    const updated = await store.update(rejectDurableMemory(existing, Date.now()))
    return c.json({ ok: true, item: updated })
  })

  app.delete("/v1/owner/memories/:memoryId", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const memoryId = c.req.param("memoryId")
    const ok = await store.delete(memoryId)
    if (!ok) return c.json({ ok: false, reason: "not found" }, 404)
    return c.json({ ok: true, memoryId })
  })

  app.get("/v1/owner/documents", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.documentStore
    if (!store) return c.json({ ok: false, reason: "document store unavailable" }, 503)
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const items = await store.listBySubject({ subject, limit: 100 })
    return c.json({
      items: items.map((d) => ({
        ...d,
        extractedText:
          d.extractedText.length > 500
            ? `${d.extractedText.slice(0, 500)}…`
            : d.extractedText,
      })),
    })
  })

  app.get("/v1/owner/documents/:documentId", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.documentStore
    if (!store) return c.json({ ok: false, reason: "document store unavailable" }, 503)
    const item = await store.get(c.req.param("documentId"))
    if (!item) return c.json({ ok: false, reason: "not found" }, 404)
    return c.json({ ok: true, item })
  })

  app.post("/v1/owner/documents", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.documentStore
    if (!store) return c.json({ ok: false, reason: "document store unavailable" }, 503)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
      readonly title?: string
      readonly format?: string
      readonly text?: string
      readonly mimeType?: string
      readonly byteSize?: number
      readonly provenance?: Record<string, unknown>
    }
    const format = parseDocumentFormat(body.format ?? "plaintext")
    if (!format) {
      return c.json(
        { ok: false, reason: "unsupported format (plaintext|markdown|pdf)" },
        400,
      )
    }
    const created = ingestDocumentRecord({
      subject: body.subject ?? "owner",
      title: body.title ?? "",
      format,
      text: body.text ?? "",
      ...(typeof body.mimeType === "string" ? { mimeType: body.mimeType } : {}),
      ...(typeof body.byteSize === "number" ? { byteSize: body.byteSize } : {}),
      ...(body.provenance
        ? {
            provenance: {
              ...(typeof body.provenance["conversationId"] === "string"
                ? { conversationId: body.provenance["conversationId"] }
                : {}),
              ...(typeof body.provenance["messageId"] === "string"
                ? { messageId: body.provenance["messageId"] }
                : {}),
              ...(typeof body.provenance["sourcePath"] === "string"
                ? { sourcePath: body.provenance["sourcePath"] }
                : {}),
              ...(typeof body.provenance["note"] === "string"
                ? { note: body.provenance["note"] }
                : {}),
            },
          }
        : {}),
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    const saved = await store.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.post("/v1/owner/documents/:documentId/promote-memory", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const docs = wiring.documentStore
    const memories = wiring.durableMemoryStore
    if (!docs || !memories) {
      return c.json({ ok: false, reason: "document or memory store unavailable" }, 503)
    }
    const documentId = c.req.param("documentId")
    const doc = await docs.get(documentId)
    if (!doc) return c.json({ ok: false, reason: "not found" }, 404)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly content?: string
      readonly status?: string
    }
    const content =
      (typeof body.content === "string" && body.content.trim()
        ? body.content.trim()
        : `${doc.title}: ${doc.extractedText}`
      ).slice(0, 4000)
    const created = createDurableMemoryRecord({
      subject: doc.subject,
      content,
      sourceKind: "document",
      status:
        body.status === "confirmed" || body.status === "candidate" ? body.status : "candidate",
      provenance: {
        documentId: doc.id,
        ...(doc.provenance.conversationId
          ? { conversationId: doc.provenance.conversationId }
          : {}),
        note: `promoted from document ${doc.title}`,
      },
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    const saved = await memories.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.get("/v1/owner/project-knowledge", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.projectKnowledgeStore
    if (!store) return c.json({ ok: false, reason: "project knowledge store unavailable" }, 503)
    const projectId = (c.req.query("projectId") ?? "").trim()
    if (!projectId) return c.text("projectId query required", 400)
    const items = await store.listByProject({ projectId, limit: 100 })
    return c.json({
      items: items.map((item) => ({
        ...item,
        body: item.body.length > 500 ? `${item.body.slice(0, 500)}…` : item.body,
      })),
    })
  })

  app.get("/v1/owner/project-knowledge/:itemId", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.projectKnowledgeStore
    if (!store) return c.json({ ok: false, reason: "project knowledge store unavailable" }, 503)
    const item = await store.get(c.req.param("itemId"))
    if (!item) return c.json({ ok: false, reason: "not found" }, 404)
    return c.json({ ok: true, item })
  })

  app.post("/v1/owner/project-knowledge", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.projectKnowledgeStore
    if (!store) return c.json({ ok: false, reason: "project knowledge store unavailable" }, 503)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly projectId?: string
      readonly title?: string
      readonly kind?: string
      readonly text?: string
      readonly filePath?: string
      readonly provenance?: Record<string, unknown>
    }
    const projectId = (body.projectId ?? "").trim()
    if (!projectId) return c.json({ ok: false, reason: "projectId is required" }, 400)

    const kindRaw = (body.kind ?? "manual_note").trim() as ProjectKnowledgeKind
    if (kindRaw === "ingested_document") {
      return c.json(
        { ok: false, reason: "use promote-project-knowledge for ingested_document" },
        400,
      )
    }

    let text = typeof body.text === "string" ? body.text : ""
    let sourcePath: string | undefined
    if (typeof body.filePath === "string" && body.filePath.trim()) {
      const root = workspaceRootFrom({ workspaceRoot: process.env["BUTLER_V5_WORKSPACE_ROOT"] })
      const resolved = resolveUnderWorkspace(root, body.filePath.trim())
      if (!resolved.ok) return c.json({ ok: false, reason: resolved.reason }, 400)
      try {
        text = readFileSync(resolved.path, "utf8")
        sourcePath = body.filePath.trim()
      } catch (err) {
        return c.json(
          {
            ok: false,
            reason: err instanceof Error ? err.message : String(err),
          },
          400,
        )
      }
    }

    const created = createProjectKnowledgeRecord({
      projectId,
      title: body.title ?? (sourcePath ? sourcePath : "note"),
      kind: kindRaw === "file_snapshot" || sourcePath ? "file_snapshot" : kindRaw,
      body: text,
      ...(body.provenance || sourcePath
        ? {
            provenance: {
              ...(sourcePath ? { sourcePath } : {}),
              ...(typeof body.provenance?.["note"] === "string"
                ? { note: body.provenance["note"] }
                : {}),
            },
          }
        : {}),
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    const saved = await store.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.post("/v1/owner/project-knowledge/sync", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.projectKnowledgeStore
    if (!store) return c.json({ ok: false, reason: "project knowledge store unavailable" }, 503)
    const loaded = loadProjectKnowledgeSourcesFromEnv(process.env)
    if (loaded.kind === "none") {
      return c.json({ ok: false, reason: "no sources manifest configured" }, 400)
    }
    if (loaded.kind === "error") {
      return c.json({ ok: false, reason: loaded.reason }, 400)
    }
    const stats = await syncProjectKnowledgeFromManifest({
      wiring,
      manifest: loaded.manifest,
      env: process.env,
    })
    return c.json({ ok: true, stats, watchEnabled: isProjectKnowledgeWatchEnabled(process.env) })
  })

  app.delete("/v1/owner/project-knowledge/:itemId", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.projectKnowledgeStore
    if (!store) return c.json({ ok: false, reason: "project knowledge store unavailable" }, 503)
    const itemId = c.req.param("itemId")
    const ok = await store.delete(itemId)
    if (!ok) return c.json({ ok: false, reason: "not found" }, 404)
    return c.json({ ok: true, itemId })
  })

  app.post("/v1/owner/documents/:documentId/promote-project-knowledge", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const docs = wiring.documentStore
    const pk = wiring.projectKnowledgeStore
    if (!docs || !pk) {
      return c.json({ ok: false, reason: "document or project knowledge store unavailable" }, 503)
    }
    const documentId = c.req.param("documentId")
    const doc = await docs.get(documentId)
    if (!doc) return c.json({ ok: false, reason: "not found" }, 404)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly projectId?: string
      readonly title?: string
    }
    const projectId = (body.projectId ?? c.req.query("projectId") ?? "").trim()
    if (!projectId) return c.json({ ok: false, reason: "projectId is required" }, 400)
    const created = projectKnowledgeFromDocument({
      projectId,
      document: doc,
      ...(typeof body.title === "string" && body.title.trim() ? { title: body.title } : {}),
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    const saved = await pk.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.delete("/v1/owner/documents/:documentId", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.documentStore
    if (!store) return c.json({ ok: false, reason: "document store unavailable" }, 503)
    const documentId = c.req.param("documentId")
    const ok = await store.delete(documentId)
    if (!ok) return c.json({ ok: false, reason: "not found" }, 404)
    const cascaded =
      (await wiring.durableMemoryStore?.deleteBySourceDocumentId(documentId)) ?? 0
    const cascadedProjectKnowledge =
      (await wiring.projectKnowledgeStore?.deleteBySourceDocumentId(documentId)) ?? 0
    return c.json({
      ok: true,
      documentId,
      cascadedMemories: cascaded,
      cascadedProjectKnowledge,
    })
  })

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

  app.get("/v1/owner/mcp/status", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const env = process.env
    const enabled = isMcpEnabled(env)
    const bundle = wiring.mcp
    const now = new Date()
    const servers =
      bundle.servers.length > 0
        ? bundle.servers
        : bundle.runtimeTools.length > 0
          ? [
              {
                serverId: mcpServerIdFromEnv(env),
                mode: bundle.mode,
                discovered: bundle.discovered,
              },
            ]
          : []
    const activeGrantsByServer: Record<string, number> = {}
    let activeGrants = 0
    if (enabled) {
      for (const server of servers) {
        const count = await wiring.runtimeStore.countActiveScopedGrantsForMcpServer(
          server.serverId,
          now,
        )
        activeGrantsByServer[server.serverId] = count
        activeGrants += count
      }
    }
    const manifestLoaded = loadMcpManifestFromEnv(env)
    return c.json({
      enabled,
      mode: bundle.mode,
      tools: bundle.runtimeTools.map((t) => t.name),
      discovered: bundle.discovered.map((t) => t.name),
      servers: servers.map((server) => {
        const manifestServer =
          manifestLoaded.kind === "loaded"
            ? resolveMcpManifestServer(manifestLoaded.manifest, server.serverId)
            : null
        const provider = manifestServer
          ? mcpProviderMetadataFromManifest({
              serverId: server.serverId,
              ...(manifestServer.defaultRisk ? { defaultRisk: manifestServer.defaultRisk } : {}),
              ...(manifestServer.defaultSandboxProfile
                ? { defaultSandboxProfile: manifestServer.defaultSandboxProfile }
                : {}),
              ...(manifestServer.auditPolicy ? { auditPolicy: manifestServer.auditPolicy } : {}),
            })
          : defaultMcpProviderMetadata(server.serverId)
        return {
          serverId: server.serverId,
          mode: server.mode,
          tools: bundle.runtimeTools
            .filter((tool) => bundle.serverIdByCapability[tool.name as string] === server.serverId)
            .map((tool) => tool.name),
          discovered: server.discovered.map((tool) => tool.name),
          activeGrants: activeGrantsByServer[server.serverId] ?? 0,
          provider,
        }
      }),
      activeGrants,
    })
  })

  app.post("/v1/owner/mcp/servers/:serverId/revoke-grants", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const serverId = c.req.param("serverId").trim()
    if (!serverId) return c.text("serverId required", 400)
    const body = (await c.req.json().catch(() => ({}))) as { readonly subject?: string }
    const now = new Date()
    const revoked = await revokeScopedGrantsForMcpServer(wiring.runtimeStore, serverId, now)
    await wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: null,
      action: "mcp.grants_revoked",
      subject: body.subject ?? "owner",
      detail: { serverId, revoked },
      createdAt: now,
    })
    return c.json({ ok: true, serverId, revoked })
  })
}
