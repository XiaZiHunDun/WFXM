import type { Hono } from "hono"
import {
  approveWaitingStep,
  denyWaitingStep,
  parsePendingCapabilityInput,
} from "@butler/runtime/approval-runtime.js"
import { cancelRunCascade, expireOverdueRuns } from "@butler/runtime/run-lifecycle.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { resumeApprovedCapability } from "../approval-resume.js"
import {
  assertOwnerApprovalRunTrigger,
  buildOwnerApprovalRunTrigger,
} from "../owner-approval-trigger.js"

/**
 * Owner control-surface routes for approvals and run lifecycle.
 * Split from owner-routes.ts (file-size gate) — behavior unchanged.
 */
export function registerApprovalsRunsRoutes(app: Hono, wiring: Wiring): void {
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
}
