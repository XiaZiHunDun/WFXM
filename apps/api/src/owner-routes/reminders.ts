import type { Hono } from "hono"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { safeOwnerError } from "../safe-owner-error.js"
import { unauthorizedForOwner } from "../owner-jargon.js"

/**
 * Owner read-only reminder view (debugging / acceptance).
 * Mutations stay in chat tools so ownership + audit stay on one path.
 */
export function registerReminderRoutes(app: Hono, wiring: Wiring): void {
  app.get("/v1/owner/reminders", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    if (!wiring.reminderStore) return c.json({ items: [] })
    try {
      const rows = await wiring.reminderStore.listActive()
      const items = rows.map((row) => ({
        id: row.id,
        subject: row.subject,
        content: row.content,
        fireAtMs: row.fireAtMs,
        fireAt: new Date(row.fireAtMs).toISOString(),
        repeat: row.repeat,
        status: row.status,
        attemptCount: row.attemptCount,
        ...(row.lastError === null ? {} : { lastError: row.lastError }),
      }))
      return c.json({ items })
    } catch (err) {
      return c.json(
        {
          ok: false,
          reason: safeOwnerError(err, "读取提醒失败，请稍后重试", {
            operation: "owner-reminders-list",
          }),
        },
        400,
      )
    }
  })
}
