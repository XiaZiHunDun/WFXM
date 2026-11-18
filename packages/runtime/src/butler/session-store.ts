import type { ButlerSessionRecord, ButlerSessionStore } from "@butler/ports/core/butler-session.js"

/** In-memory session store; the delivery shell can swap in a durable one. */
export class MemoryButlerSessionStore implements ButlerSessionStore {
  private readonly records = new Map<string, ButlerSessionRecord>()

  async load(conversationId: string): Promise<ButlerSessionRecord | null> {
    return this.records.get(conversationId) ?? null
  }

  async save(record: ButlerSessionRecord): Promise<void> {
    this.records.set(record.conversationId, record)
  }

  async delete(conversationId: string): Promise<void> {
    this.records.delete(conversationId)
  }

  list(): readonly ButlerSessionRecord[] {
    return [...this.records.values()]
  }
}
