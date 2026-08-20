import { eq } from "drizzle-orm"
import type { Hono } from "hono"
import { auditEvents, scopedGrants, steps } from "@butler/persistence"
import type { Wiring } from "./wiring.js"

function ownerAuthorized(c: { req: { header: (name: string) => string | undefined } }): boolean {
  const expected = (process.env["BUTLER_V5_OWNER_TOKEN"] ?? "").trim()
  if (!expected) return false
  const auth = c.req.header("authorization") ?? ""
  return auth === `Bearer ${expected}`
}

export function createOwnerRoutes(app: Hono, wiring: Wiring): void {
  app.get("/v1/owner/approvals", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const rows = await wiring.db.select().from(steps).where(eq(steps.status, "waiting"))
    return c.json({ items: rows })
  })

  app.post("/v1/owner/approvals/:stepId/approve", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const stepId = c.req.param("stepId")
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
      readonly capabilities?: readonly string[]
      readonly maxUses?: number
      readonly ttlSeconds?: number
      readonly runId?: string
    }

    await wiring.db
      .update(steps)
      .set({ status: "succeeded", updatedAt: new Date() })
      .where(eq(steps.stepId, stepId))

    await wiring.db.insert(scopedGrants).values({
      grantId: crypto.randomUUID(),
      runId: body.runId ?? crypto.randomUUID(),
      subject: body.subject ?? "owner",
      scope: { capabilities: body.capabilities ?? [] },
      remainingUses: body.maxUses ?? 1,
      expiresAt: new Date(Date.now() + (body.ttlSeconds ?? 900) * 1000),
      createdAt: new Date(),
    })

    await wiring.db.insert(auditEvents).values({
      auditId: crypto.randomUUID(),
      runId: body.runId ?? null,
      conversationId: null,
      action: "approval.granted",
      subject: body.subject ?? "owner",
      detail: { stepId, capabilities: body.capabilities ?? [] },
      createdAt: new Date(),
    })

    return c.json({ ok: true, stepId })
  })

  app.post("/v1/owner/approvals/:stepId/deny", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const stepId = c.req.param("stepId")
    await wiring.db
      .update(steps)
      .set({ status: "failed", updatedAt: new Date() })
      .where(eq(steps.stepId, stepId))

    await wiring.db.insert(auditEvents).values({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: null,
      action: "approval.denied",
      subject: "owner",
      detail: { stepId },
      createdAt: new Date(),
    })

    return c.json({ ok: true, stepId })
  })
}
