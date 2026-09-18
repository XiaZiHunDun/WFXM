import type { Hono } from "hono"
import { denyWaitingStep, parsePendingCapabilityInput } from "@butler/runtime/approval-runtime.js"
import { cancelRunCascade, expireOverdueRuns } from "@butler/runtime/run-lifecycle.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { safeOwnerError } from "../safe-owner-error.js"
import { handleApproveStep } from "./approvals-approve.js"

/**
 * Owner control-surface routes for approvals and run lifecycle.
 * Split from owner-routes.ts (file-size gate) — behavior unchanged.
 *
 * D65 T2d: largest handler (`approvals/:stepId/approve`, ~88 lines) extracted
 * to `approvals-approve.ts` for per-file readability. Re-exported here is
 * unnecessary — call sites use `handleApproveStep` directly.
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

  app.post("/v1/owner/approvals/:stepId/approve", (c) => handleApproveStep(c, wiring))

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
          reason: safeOwnerError(err, "拒绝操作失败，请稍后重试", {
            operation: "approvals-deny",
            stepId,
          }),
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
        return c.json({ ok: false, reason: "未找到对应 run" }, 404)
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
          reason: safeOwnerError(err, "取消运行失败，请稍后重试", {
            operation: "runs-cancel",
            runId: c.req.param("runId"),
          }),
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
          reason: safeOwnerError(err, "清理超时运行失败，请稍后重试", {
            operation: "runs-expire-overdue",
          }),
        },
        400,
      )
    }
  })
}
