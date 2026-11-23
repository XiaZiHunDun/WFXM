/**
 * Butler -> subagent dispatch port.
 *
 * Keeps the butler runtime free of the delegate/outbox details: whether a
 * subagent is enabled, which capabilities are allowed and how the child
 * conversation is created are the composition root's concern.
 */

export interface ButlerSubagentRequest {
  readonly task: string
  readonly conversationId: string
  readonly userId: string
  readonly role?: string
  readonly capabilities?: readonly string[]
}

export type ButlerSubagentResult =
  { readonly ok: true; readonly output: string } | { readonly ok: false; readonly reason: string }

export interface ButlerSubagentPort {
  delegate(input: ButlerSubagentRequest): Promise<ButlerSubagentResult>
}
