import { claimOutbox, completeOutbox, failOutbox } from "./outbox.js"
import type { OutboxMessage } from "./outbox.js"
import type { ButlerDb } from "./db.js"

type Handler = (msg: OutboxMessage) => Promise<void>

/**
 * Process up to one batch of claimed messages.
 * Returns the count successfully delivered in this run.
 */
export async function runWorkerOnce(
  db: ButlerDb,
  workerId: string,
  leaseMs: number,
  handler: Handler,
): Promise<number> {
  const claimed = await claimOutbox(db, workerId, leaseMs)
  let delivered = 0
  for (const msg of claimed) {
    try {
      await handler(msg)
      await completeOutbox(db, msg.messageId)
      delivered++
    } catch (err) {
      await failOutbox(db, msg.messageId, err instanceof Error ? err.message : String(err))
    }
  }
  return delivered
}
