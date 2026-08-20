export interface RunCoordinatorOptions {
  readonly waitTimeoutMs?: number
}

type Release = () => void

/**
 * Ensures at most one active main Run executes per conversation in-process.
 * Additional triggers wait until the active Run releases the lock or timeout.
 */
export class RunCoordinator {
  private readonly locks = new Map<string, Promise<void>>()
  private readonly releasers = new Map<string, Release>()
  private readonly waitTimeoutMs: number

  constructor(options: RunCoordinatorOptions = {}) {
    this.waitTimeoutMs = options.waitTimeoutMs ?? 120_000
  }

  async withConversationLock<T>(conversationId: string, fn: () => Promise<T>): Promise<T> {
    await this.acquire(conversationId)
    try {
      return await fn()
    } finally {
      this.release(conversationId)
    }
  }

  private async acquire(conversationId: string): Promise<void> {
    const deadline = Date.now() + this.waitTimeoutMs
    while (this.locks.has(conversationId)) {
      if (Date.now() >= deadline) {
        throw new Error(`conversation lock timeout for ${conversationId}`)
      }
      await this.locks.get(conversationId)
      await new Promise((resolve) => setTimeout(resolve, 0))
    }

    let release!: Release
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    this.locks.set(conversationId, gate)
    this.releasers.set(conversationId, release)
  }

  private release(conversationId: string): void {
    const release = this.releasers.get(conversationId)
    release?.()
    this.releasers.delete(conversationId)
    this.locks.delete(conversationId)
  }
}
