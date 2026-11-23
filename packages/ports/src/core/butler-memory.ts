/**
 * P4.2: butler-layer memory port.
 *
 * The butler runtime projects finished sessions into user-scope memory; it
 * never imports a memory store. `agent-rag` supplies the adapter at the
 * composition root. Native transcripts stay in the butler session store.
 */

export type ButlerMemoryKind =
  "profile" | "preference" | "relationship" | "commitment" | "convention" | "note"

export interface ButlerMemoryFact {
  readonly title: string
  readonly text: string
  readonly kind?: ButlerMemoryKind
  readonly tags?: readonly string[]
}

export interface ButlerProfileSnapshot {
  readonly displayName?: string
  readonly communicationStyle?: string
  readonly preferences?: readonly string[]
  readonly commitments?: readonly string[]
  readonly relationships?: readonly {
    readonly name: string
    readonly relation: string
    readonly notes?: string
  }[]
}

export interface ButlerSessionSummaryEvent {
  readonly userId: string
  readonly sessionId: string
  readonly summary: string
  readonly profile?: ButlerProfileSnapshot
  readonly facts?: readonly ButlerMemoryFact[]
  readonly occurredAt: string
}

export interface RecalledUserMemory {
  readonly title: string
  readonly text: string
}

export interface ButlerMemoryPort {
  recordSessionSummary(event: ButlerSessionSummaryEvent): Promise<void>
  /** Optional: explicit owner instruction ("记住：…") outside a session summary. */
  rememberUserMemory?(input: {
    readonly userId: string
    readonly fact: ButlerMemoryFact
  }): Promise<void>
  /** Optional: recall user-scope memory before a butler agent turn. */
  recallUserMemory?(
    query: string,
    limit?: number,
    userId?: string,
  ): Promise<readonly RecalledUserMemory[]>
}
