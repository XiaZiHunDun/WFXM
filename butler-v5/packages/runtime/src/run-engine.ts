import type { RunTrigger, RuntimeStore, StoredRun } from "@butler/domain/runtime.js"
import { isActiveMainRunStatus, runBudgetWithTrigger, validateRunTrigger } from "@butler/domain/runtime.js"
import { RunCoordinator } from "./run-coordinator.js"
import { resumeFromWaitingExternal, transitionRunToTerminal } from "./run-lifecycle.js"
import { buildWorkingSet, type WorkingSetResult } from "./working-set.js"
import {
  filterDevHistoryNoise,
  resolveWorkingSetBudget,
  workingSetModeFromTriggerPayload,
  type WorkingSetMode,
} from "./working-set-budget.js"
import { getSharedLocalTracer } from "./observability/local-tracer.js"
import { systemClock, type ClockPort } from "@butler/ports/core/clock.js"

export class RunPauseForApproval extends Error {
  constructor(public readonly payload: unknown) {
    super("run paused for approval")
  }
}

/** Thrown when an inbound RunTrigger fails `validateRunTrigger` (P3-1 seam, fail-closed). */
export class InvalidRunTriggerError extends Error {
  constructor(public readonly reason: string) {
    super(`invalid RunTrigger: ${reason}`)
  }
}

/** Thrown when start would race an existing active main Run for the conversation. */
export class ActiveMainRunConflict extends Error {
  constructor(
    public readonly conversationId: string,
    public readonly activeRun: StoredRun,
  ) {
    super(
      `conversation ${conversationId} already has active main Run ${activeRun.id} (${activeRun.status}); resume that Run instead of creating a new one`,
    )
  }
}

export interface RunEngineContext {
  readonly conversationId: string
  readonly messageId: string
  readonly runId: string
  readonly workingSet: WorkingSetResult
  /** True when this invocation resumed an existing Run rather than creating one. */
  readonly resumed: boolean
}

export interface InboundRunInput {
  readonly conversationId: string
  readonly messageId: string
  readonly subject: string
  readonly content: string
  readonly idempotencyKey: string
  readonly projectId?: string
  readonly trigger?: RunTrigger
  readonly triggerSource?: RunTrigger["source"]
  readonly goal?: string
  readonly budget?: Readonly<Record<string, unknown>>
  /** Optional Run deadline (Schedule / heartbeat uses this). */
  readonly deadline?: Date | null
  /** Override working-set budget mode (default reads trigger.payload.workingSetMode). */
  readonly workingSetMode?: WorkingSetMode
}

export interface ResumeRunInput {
  readonly runId: string
  readonly conversationId: string
  /** Optional trailing user text for working-set construction (e.g.「确认」). */
  readonly content?: string
  readonly messageId?: string
}

function isTrustedInboundTrigger(trigger: RunTrigger | undefined): boolean {
  const level = trigger?.trustLevel
  return level === "trusted" || level === "owner"
}

function resolveInboundWorkingSetMode(
  input: InboundRunInput,
  run?: StoredRun,
): WorkingSetMode {
  if (input.workingSetMode) return input.workingSetMode
  const fromInputTrigger = workingSetModeFromTriggerPayload(input.trigger?.payload)
  if (fromInputTrigger === "dev") return "dev"
  return workingSetModeFromTriggerPayload(
    run?.budget?.["triggerPayload"] as Readonly<Record<string, unknown>> | undefined,
  )
}

export class RunEngine {
  private readonly coordinator: RunCoordinator

  constructor(
    private readonly store: RuntimeStore,
    coordinator?: RunCoordinator,
    private readonly clock: ClockPort = systemClock,
  ) {
    this.coordinator = coordinator ?? new RunCoordinator()
  }

  /**
   * Start the single active main Run for a conversation.
   * Refuses to create when an active main Run already exists — callers must
   * `resumeRun` (approval / waiting_external) instead of opening a competing Run.
   *
   * Exception: trusted/owner inbound against `waiting_external` auto-resumes
   * the same Run (DESIGN: 后续可信消息恢复原 Run).
   */
  async executeInbound<T>(
    input: InboundRunInput,
    runBody: (ctx: RunEngineContext) => Promise<T>,
  ): Promise<T> {
    // P3-1 seam: when an adapter hands us a normalized RunTrigger, it MUST be
    // valid (subject + idempotencyKey + channel/webhook conversationRef). Fail
    // closed so no new entry can bypass the trigger contract.
    if (input.trigger) {
      const check = validateRunTrigger(input.trigger)
      if (!check.ok) throw new InvalidRunTriggerError(check.reason)
    }
    return this.coordinator.withConversationLock(input.conversationId, async () => {
      const existing = await this.store.findActiveMainRun(input.conversationId)
      if (existing && isActiveMainRunStatus(existing.status)) {
        if (existing.status === "waiting_external" && isTrustedInboundTrigger(input.trigger)) {
          return this.resumeWaitingExternalInbound(input, existing, runBody)
        }
        throw new ActiveMainRunConflict(input.conversationId, existing)
      }

      const createdAt = this.clock.now()
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
        ...(input.projectId ? { projectId: input.projectId } : {}),
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
        deadline: input.deadline === undefined ? null : input.deadline,
        createdAt,
      })
      const running = await this.store.transitionRunStatus(
        run.id,
        run.version,
        "running",
        new Date(createdAt.getTime() + 1),
      )
      return this.runBodyAndFinalize({
        conversationId: inbound.conversationId,
        messageId: inbound.messageId,
        run: running,
        content: input.content,
        resumed: false,
        workingSetMode: resolveInboundWorkingSetMode(input, running),
        runBody,
      })
    })
  }

  /**
   * Resume an existing main Run (same runId) after approval or waiting_external.
   * Does not create a new Run or inbound user message. Expects status `running`
   * (approveWaitingStep already transitions waiting_approval → running).
   */
  async resumeRun<T>(
    input: ResumeRunInput,
    runBody: (ctx: RunEngineContext) => Promise<T>,
  ): Promise<T> {
    return this.coordinator.withConversationLock(input.conversationId, async () => {
      const run = await this.store.getRun(input.runId)
      if (!run) {
        throw new Error(`run not found: ${input.runId}`)
      }
      if (run.conversationId !== input.conversationId) {
        throw new Error(
          `run ${input.runId} belongs to ${run.conversationId}, not ${input.conversationId}`,
        )
      }
      if (run.status !== "running") {
        throw new Error(`cannot resume run ${run.id} in status ${run.status}; expected running`)
      }
      return this.runBodyAndFinalize({
        conversationId: run.conversationId,
        messageId: input.messageId ?? `resume:${run.id}`,
        run,
        content: input.content ?? "",
        resumed: true,
        workingSetMode: workingSetModeFromTriggerPayload(
          run.budget?.["triggerPayload"] as Readonly<Record<string, unknown>> | undefined,
        ),
        runBody,
      })
    })
  }

  private async resumeWaitingExternalInbound<T>(
    input: InboundRunInput,
    existing: StoredRun,
    runBody: (ctx: RunEngineContext) => Promise<T>,
  ): Promise<T> {
    const createdAt = this.clock.now()
    const triggerSource = input.trigger?.source ?? input.triggerSource ?? "channel"
    const subject = input.trigger?.subject ?? input.subject
    const messageIdempotencyKey = input.trigger?.idempotencyKey ?? input.idempotencyKey
    await this.store.appendMessage({
      messageId: input.messageId,
      conversationId: existing.conversationId,
      role: "user",
      content: { text: input.content },
      triggerSource,
      idempotencyKey: messageIdempotencyKey,
      createdAt,
    })
    const running = await resumeFromWaitingExternal(this.store, existing.id, {
      subject,
    })
    return this.runBodyAndFinalize({
      conversationId: existing.conversationId,
      messageId: input.messageId,
      run: running,
      content: input.content,
      resumed: true,
      workingSetMode: resolveInboundWorkingSetMode(input, running),
      runBody,
    })
  }

  private async runBodyAndFinalize<T>(args: {
    readonly conversationId: string
    readonly messageId: string
    readonly run: StoredRun
    readonly content: string
    readonly resumed: boolean
    readonly workingSetMode?: WorkingSetMode
    readonly runBody: (ctx: RunEngineContext) => Promise<T>
  }): Promise<T> {
    const env = process.env
    const workingSetMode =
      args.workingSetMode ??
      workingSetModeFromTriggerPayload(args.run.budget?.["triggerPayload"] as
        | Readonly<Record<string, unknown>>
        | undefined)
    let messages = await this.store.listMessages(args.conversationId)
    if (workingSetMode === "dev") {
      messages = filterDevHistoryNoise(messages)
    }
    const workingSet = buildWorkingSet({
      messages,
      trailingUserContent: args.content,
      budget: resolveWorkingSetBudget(env, workingSetMode),
    })
    const tracer = getSharedLocalTracer()
    const startedAt = Date.now()
    tracer.record({
      kind: "run",
      name: args.resumed ? "resume" : "start",
      conversationId: args.conversationId,
      runId: args.run.id,
      parentRunId: args.run.parentRunId,
      subject: args.run.subject,
      triggerSource: args.run.triggerSource,
      detail: { resumed: args.resumed, goal: args.run.goal },
      nowMs: startedAt,
    })

    try {
      const result = await args.runBody({
        conversationId: args.conversationId,
        messageId: args.messageId,
        runId: args.run.id,
        workingSet,
        resumed: args.resumed,
      })
      // Double-completion guard: only an active Run is completed. If a
      // sweeper / owner already terminalized this Run, this is a no-op.
      const finalized = await transitionRunToTerminal(this.store, args.run.id, {
        from: ["running"],
        to: "succeeded",
        now: this.clock.now(),
        subject: args.run.subject,
      })
      tracer.record({
        kind: "run",
        name: "finish",
        status: "ok",
        conversationId: args.conversationId,
        runId: args.run.id,
        subject: args.run.subject,
        triggerSource: args.run.triggerSource,
        durationMs: Date.now() - startedAt,
        detail: { finalStatus: finalized?.status ?? "succeeded" },
      })
      return result
    } catch (err) {
      if (err instanceof RunPauseForApproval) {
        tracer.record({
          kind: "approval",
          name: "waiting_approval",
          status: "waiting",
          conversationId: args.conversationId,
          runId: args.run.id,
          subject: args.run.subject,
          durationMs: Date.now() - startedAt,
        })
        return err.payload as T
      }
      // Double-completion guard: only an active Run is failed. If a
      // sweeper / owner already terminalized this Run, this is a no-op.
      await transitionRunToTerminal(this.store, args.run.id, {
        from: ["running", "waiting_approval"],
        to: "failed",
        now: this.clock.now(),
        subject: args.run.subject,
        reason: err instanceof Error ? err.message : String(err),
      })
      tracer.record({
        kind: "run",
        name: "finish",
        status: "error",
        conversationId: args.conversationId,
        runId: args.run.id,
        subject: args.run.subject,
        durationMs: Date.now() - startedAt,
        detail: { error: err instanceof Error ? err.message : String(err) },
      })
      throw err
    }
  }
}
