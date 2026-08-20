import type { Hono } from "hono"
import { approveWaitingStep, denyWaitingStep } from "@butler/runtime/approval-runtime.js"
import { resumeApprovedCapability } from "./approval-resume.js"
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
    const rows = await wiring.runtimeStore.listWaitingApprovalSteps()
    return c.json({ items: rows })
  })

  app.post("/v1/owner/approvals/:stepId/approve", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const stepId = c.req.param("stepId")
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
    }
    try {
      const decision = await approveWaitingStep(
        wiring.runtimeStore,
        stepId,
        body.subject ?? "owner",
      )
      const resumed = await resumeApprovedCapability(wiring, decision)
      return c.json({
        ok: resumed.ok,
        stepId,
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
      await denyWaitingStep(wiring.runtimeStore, stepId, "owner")
      return c.json({ ok: true, stepId })
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
}
