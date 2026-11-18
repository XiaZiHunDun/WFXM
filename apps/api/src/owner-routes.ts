import type { Hono } from "hono"
import type { Wiring } from "./wiring.js"
import { registerConversationsScheduleRoutes } from "./owner-routes/conversations-schedule.js"
import { registerApprovalsRunsRoutes } from "./owner-routes/approvals-runs.js"
import { registerMemoriesRoutes } from "./owner-routes/memories.js"
import { registerDocumentsRoutes } from "./owner-routes/documents.js"
import { registerProjectKnowledgeRoutes } from "./owner-routes/project-knowledge.js"
import { registerTracesProceduresTasksRoutes } from "./owner-routes/traces-procedures-tasks.js"
import { registerUsageRoutes } from "./owner-routes/usage.js"
import { registerMcpRoutes } from "./owner-routes/mcp.js"
import { registerAuditFatigueRoutes } from "./owner-routes/audit-fatigue.js"
import { tryAcquireOwnerSlot } from "./lib/owner-rate-limit.js"

/**
 * Owner control-surface routes — aggregation entry.
 * Route implementations live in ./owner-routes/ submodules (split to stay
 * under the file-size gate); behavior unchanged.
 *
 * D70 T4 (audit #11 SEC-002): in-memory sliding-window throttle on every
 * /v1/owner/* path. Constant 120/min by default (env-tunable). Closes
 * the per-IP/per-subject burst-amplification gap on expensive endpoints
 * (audit/fatigue/replay caps batch at 1000 ids; documents/memories have
 * no batch cap at all). The throttle key is "owner" for the loopback
 * control surface — when bearer auth lands (D71+) the key switches to
 * the authenticated subject.
 */
export function createOwnerRoutes(app: Hono, wiring: Wiring): void {
  app.use("/v1/owner/*", async (c, next) => {
    if (!tryAcquireOwnerSlot("owner", process.env)) {
      // D71 T4 (audit #12 SO-005): owner-jargon Chinese message. D70 T4
      // closed the throttle but left the operator English string "rate
      // limit exceeded" — owner UI sees this verbatim. Return Chinese
      // with a brief cooldown hint matching the operator fallback style.
      return c.text("请求过于频繁，请稍后再试", 429)
    }
    await next()
  })
  registerConversationsScheduleRoutes(app, wiring)
  registerApprovalsRunsRoutes(app, wiring)
  registerMemoriesRoutes(app, wiring)
  registerDocumentsRoutes(app, wiring)
  registerProjectKnowledgeRoutes(app, wiring)
  registerTracesProceduresTasksRoutes(app, wiring)
  registerUsageRoutes(app, wiring)
  registerMcpRoutes(app, wiring)
  registerAuditFatigueRoutes(app, wiring)
}
