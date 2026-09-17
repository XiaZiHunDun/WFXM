/**
 * D65 T2d — Extract `approvals/:stepId/approve` handler from approvals-runs.ts.
 *
 * Owner-facing approval decision path: validates trigger, records grant via
 * `approveWaitingStep`, then resumes the gated capability. D63 T1 (audit #9
 * F-11) classifies `alreadyProcessed` into owner-jargon Chinese phrases before
 * surfacing to the HTTP API caller; raw internal reasons stay inside the
 * runtime.
 *
 * Behavior unchanged from original inline handler. D44 y/👌 inline-approval
 * continues to call this through the chat-side path; chat-side trigger is
 * built here so both flows share the same validation gate.
 */
import type { Context } from "hono"
import {
  approveWaitingStep,
  parsePendingCapabilityInput,
} from "@butler/runtime/approval-runtime.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { resumeApprovedCapability } from "../approval-resume.js"
import { safeOwnerError } from "../safe-owner-error.js"
import {
  assertOwnerApprovalRunTrigger,
  buildOwnerApprovalRunTrigger,
} from "../owner-approval-trigger.js"

export async function handleApproveStep(c: Context, wiring: Wiring): Promise<Response> {
  if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
  // Route param is guaranteed by the registered route path
  // `/v1/owner/approvals/:stepId/approve`. `?? ""` mirrors memories-rollback.ts
  // (T2a) / tasks-run.ts (T2b) / documents-promote-memory.ts (T2c) because the
  // extracted Context type loses Hono's route narrowing that the inline
  // closure had.
  const stepId = c.req.param("stepId") ?? ""
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
      // D70 T3 (audit #11 SO-015): Chinese owner-jargon. Original was
      // English "invalid pending capability step" — leaks operator
      // vocabulary "capability" to the owner-facing reply.
      return c.json({ ok: false, reason: "审批步骤已失效，请重新发起" }, 400)
    }
    if (decision._tag === "alreadyProcessed") {
      // D63 T1 (audit #9 F-11): classify alreadyProcessed reason into
      // owner-jargon before surfacing to the HTTP API caller. Raw
      // decision.reason is internal (e.g. "step already terminal
      // (waiting)" or "expired"); map to a stable Chinese phrase.
      // Map by reason string match; fall back to generic "该审批已处理"
      // if the reason doesn't match a known internal status.
      const rawReason = String(decision.reason ?? "")
      const ownerReason = rawReason.includes("expired")
        ? "审批已过期"
        : rawReason.includes("already terminal")
          ? "该审批已处理"
          : rawReason.includes("already approved")
            ? "该审批已通过"
            : rawReason.includes("already denied")
              ? "该审批已拒绝"
              : "该审批已处理"
      return c.json({ ok: true, stepId, alreadyProcessed: true, reason: ownerReason })
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
        reason: safeOwnerError(err, "审批操作失败，请稍后重试", {
          operation: "approvals-approve",
          stepId: c.req.param("stepId"),
        }),
      },
      400,
    )
  }
}
