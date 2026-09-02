import type { Hono } from "hono"
import type { Wiring } from "./wiring.js"
import { registerConversationsScheduleRoutes } from "./owner-routes/conversations-schedule.js"
import { registerApprovalsRunsRoutes } from "./owner-routes/approvals-runs.js"
import { registerMemoriesRoutes } from "./owner-routes/memories.js"
import { registerDocumentsRoutes } from "./owner-routes/documents.js"
import { registerProjectKnowledgeRoutes } from "./owner-routes/project-knowledge.js"
import { registerTracesProceduresTasksRoutes } from "./owner-routes/traces-procedures-tasks.js"
import { registerMcpRoutes } from "./owner-routes/mcp.js"

/**
 * Owner control-surface routes — aggregation entry.
 * Route implementations live in ./owner-routes/ submodules (split to stay
 * under the file-size gate); behavior unchanged.
 */
export function createOwnerRoutes(app: Hono, wiring: Wiring): void {
  registerConversationsScheduleRoutes(app, wiring)
  registerApprovalsRunsRoutes(app, wiring)
  registerMemoriesRoutes(app, wiring)
  registerDocumentsRoutes(app, wiring)
  registerProjectKnowledgeRoutes(app, wiring)
  registerTracesProceduresTasksRoutes(app, wiring)
  registerMcpRoutes(app, wiring)
}
