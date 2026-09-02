import type { Hono } from "hono"
import {
  createProjectKnowledgeRecord,
  type ProjectKnowledgeKind,
} from "@butler/domain/knowledge/project-knowledge.js"
import { readFileSync } from "node:fs"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { resolveUnderWorkspace, workspaceRootFrom } from "../workspace-tools.js"
import {
  loadProjectKnowledgeSourcesFromEnv,
  isProjectKnowledgeWatchEnabled,
} from "../project-knowledge-sources-config.js"
import { syncProjectKnowledgeFromManifest } from "../project-knowledge-sync.js"

/**
 * Owner control-surface routes for project knowledge, including file-backed
 * snapshots and manifest sync. Split from owner-routes.ts (file-size gate) —
 * behavior unchanged.
 */
export function registerProjectKnowledgeRoutes(app: Hono, wiring: Wiring): void {
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
      const rootEnv = process.env["BUTLER_V5_WORKSPACE_ROOT"]
      const root = workspaceRootFrom({
        ...(rootEnv === undefined ? {} : { workspaceRoot: rootEnv }),
      })
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
}
