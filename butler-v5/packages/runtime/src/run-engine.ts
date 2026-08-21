import type { RunTrigger, RuntimeStore } from "@butler/domain/runtime.js"
import { runBudgetWithTrigger } from "@butler/domain/runtime.js"
import { RunCoordinator } from "./run-coordinator.js"
import { buildWorkingSet, type WorkingSetResult } from "./working-set.js"

export class RunPauseForApproval extends Error {
  constructor(public readonly payload: unknown) {
    super("run paused for approval")
  }
}

export interface RunEngineContext {
  readonly conversationId: string
  readonly messageId: string
  readonly runId: string
  readonly workingSet: WorkingSetResult
}

export interface InboundRunInput {
  readonly conversationId: string
  readonly messageId: string
  readonly subject: string
  readonly content: string
  readonly idempotencyKey: string
  readonly trigger?: RunTrigger
  readonly triggerSource?: RunTrigger["source"]
  readonly goal?: string
  readonly budget?: Readonly<Record<string, unknown>>
}

export class RunEngine {
  private readonly coordinator: RunCoordinator

  constructor(
    private readonly store: RuntimeStore,
    coordinator?: RunCoordinator,
  ) {
    this.coordinator = coordinator ?? new RunCoordinator()
  }

  /** Start or resume the single active main Run for a conversation. */
  async executeInbound<T>(
    input: InboundRunInput,
    runBody: (ctx: RunEngineContext) => Promise<T>,
  ): Promise<T> {
    return this.coordinator.withConversationLock(input.conversationId, async () => {
      const createdAt = new Date()
      const triggerSource = input.trigger?.source ?? input.triggerSource ?? "channel"
      const subject = input.trigger?.subject ?? input.subject
      const messageIdempotencyKey = input.trigger?.idempotencyKey ?? input.idempotencyKey
      const runIdempotencyKey = `${messageIdempotencyKey}:run`
      const budget = input.trigger
        ? runBudgetWithTrigger(input.trigger, input.budget ?? {})
        : (input.budget ?? { maxSteps: 5 })
      const inbound = await this.store.createConversationWithUserMessage({
        conversationId: input.conversationId,
        messageId: input.messageId,
        subject,
        content: { text: input.content },
        triggerSource,
        idempotencyKey: messageIdempotencyKey,
        createdAt,
      })
      const run = await this.store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource,
        idempotencyKey: runIdempotencyKey,
        subject,
        goal: input.goal ?? "reply",
        budget,
        deadline: null,
        createdAt,
      })
      const running = await this.store.transitionRunStatus(
        run.id,
        run.version,
        "running",
        new Date(createdAt.getTime() + 1),
      )
      const messages = await this.store.listMessages(inbound.conversationId)
      const workingSet = buildWorkingSet({
        messages,
        trailingUserContent: input.content,
      })

      try {
        const result = await runBody({
          conversationId: inbound.conversationId,
          messageId: inbound.messageId,
          runId: running.id,
          workingSet,
        })
        await this.store.transitionRunStatus(running.id, running.version, "succeeded", new Date())
        return result
      } catch (err) {
        if (err instanceof RunPauseForApproval) {
          return err.payload as T
        }
        await this.store.transitionRunStatus(running.id, running.version, "failed", new Date())
        throw err
      }
    })
  }
}
