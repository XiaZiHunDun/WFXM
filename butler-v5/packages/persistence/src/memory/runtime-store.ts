/**
 * In-memory RuntimeStore — 第二持久化实现（Repository Port 物化触发，D46）。
 *
 * 生产 `runtime-store.ts`（Drizzle + postgres/PGlite）之外的第二实现：
 * 纯内存 Map，无 Drizzle / 无任何 DB / 无 IO。它实现的是同一份
 * `RuntimeStore` 合同（`@butler/domain/runtime/store-contract.js`），
 * 证明该合同是"可替换单一接缝"（Repository Port），并作为快速单测 /
 * 隔离运行 / 引导期存储的载体。
 *
 * 忠实度说明：实现核心读写语义（乐观版本续程、active-main-run 匹配、子 Run
 * 级联、授权剩余次数与过期、audit 追加）与生产实现保持一致，含 idempotencyKey
 * 去重、waiting-approval（kind==='approval' + status==='waiting'）门控、
 * listRunsPastDeadline 的 ACTIVE_MAIN_RUN_STATUSES 状态门控、findChildRuns 的
 * createdAt desc 排序、findActiveGrant 的 digest 语义（见
 * runtime-store.cross-impl.test.ts 契约线束）。对授权 scope 的 paths / MCP /
 * network 治理细则仍为简化字段匹配，不复刻 `grantMatchesAction` 全部细则；
 * 消息内容不做落库脱敏（内存非耐久转录，见 cross-impl S-B）。作为测试/隔离
 * 替代品足够，作生产持久化请用 `createRuntimeStore`。
 */
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import {
  ACTIVE_MAIN_RUN_STATUSES,
  type RuntimeStore,
  type RunStatus,
  type StoredConversation,
  type StoredMessage,
  type StoredRun,
  type StoredStep,
} from "@butler/domain/runtime.js"
import { RuntimeVersionConflictError } from "../runtime-store.js"

/** 内存内 audit 事件记录（合同无读侧，仅保留供测试断言）。 */
interface AuditEventRecord {
  readonly auditId: string
  readonly runId: string | null
  readonly conversationId: string | null
  readonly action: string
  readonly subject: string
  readonly detail: Readonly<Record<string, unknown>>
  readonly createdAt: Date
}

/**
 * 纯内存 RuntimeStore（Repository Port 的可替换实现）。
 * 每个实例独立状态，测试隔离天然成立。
 */
export function createInMemoryRuntimeStore(): RuntimeStore {
  const conversations = new Map<string, StoredConversation>()
  const messages: StoredMessage[] = []
  const runs = new Map<string, StoredRun>()
  const steps = new Map<string, StoredStep>()
  const grants = new Map<string, ScopedGrantRecord>()
  const audit: AuditEventRecord[] = []

  // 内存操作本原子；tx 参数透传但不落地。
  const withTransaction: RuntimeStore["withTransaction"] = (fn) => fn({})

  const appendAudit = (input: AuditEventRecord): void => {
    audit.push(input)
  }

  const transitionRunStatus = (
    runId: string,
    expectedVersion: number,
    status: RunStatus,
    updatedAt: Date,
  ): StoredRun => {
    const run = runs.get(runId)
    if (!run || run.version !== expectedVersion) {
      throw new RuntimeVersionConflictError(runId, expectedVersion)
    }
    const next: StoredRun = { ...run, status, version: run.version + 1, updatedAt }
    runs.set(runId, next)
    return next
  }

  return {
    async createConversationWithUserMessage(input) {
      // S-A parity: production dedups on message idempotencyKey (unique index) — a
      // re-delivered conversation+message returns the existing record, not a duplicate.
      const existing = messages.find((m) => m.idempotencyKey === input.idempotencyKey)
      if (existing) {
        return { conversationId: existing.conversationId, messageId: existing.id }
      }
      const now = input.createdAt
      conversations.set(input.conversationId, {
        id: input.conversationId,
        projectId: input.projectId ?? null,
        subject: input.subject,
        createdAt: now,
        updatedAt: now,
      })
      const message: StoredMessage = {
        id: input.messageId,
        conversationId: input.conversationId,
        role: "user",
        content: input.content,
        triggerSource: input.triggerSource,
        idempotencyKey: input.idempotencyKey,
        createdAt: now,
      }
      messages.push(message)
      return { conversationId: input.conversationId, messageId: input.messageId }
    },

    async createRun(input) {
      // S-A parity: production dedups on run idempotencyKey — re-delivery returns the
      // existing run (same id), not a duplicate.
      const existing = [...runs.values()].find(
        (r) => r.idempotencyKey === input.idempotencyKey,
      )
      if (existing) return existing
      const run: StoredRun = {
        id: input.id,
        conversationId: input.conversationId,
        parentRunId: input.parentRunId,
        triggerSource: input.triggerSource,
        idempotencyKey: input.idempotencyKey,
        subject: input.subject,
        goal: input.goal,
        budget: input.budget,
        deadline: input.deadline,
        status: "queued",
        version: 1,
        createdAt: input.createdAt,
        updatedAt: input.createdAt,
      }
      runs.set(run.id, run)
      return run
    },

    async transitionRunStatus(runId, expectedVersion, status, updatedAt) {
      return transitionRunStatus(runId, expectedVersion, status, updatedAt)
    },

    async createStep(input) {
      const step: StoredStep = {
        id: input.id,
        runId: input.runId,
        kind: input.kind,
        status: input.status,
        input: input.input,
        output: null,
        createdAt: input.createdAt,
        updatedAt: input.createdAt,
      }
      steps.set(step.id, step)
      return step
    },

    async listMessages(conversationId) {
      return messages.filter((m) => m.conversationId === conversationId)
    },

    async listConversationsByProject({ projectId, limit }) {
      const matches = [...conversations.values()]
        .filter((c) => c.projectId === projectId)
        .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())
      return limit === undefined ? matches : matches.slice(0, limit)
    },

    async appendMessage(input) {
      // S-A parity: production dedups on message idempotencyKey when present — a
      // re-delivered message returns the existing record, not a duplicate.
      if (input.idempotencyKey) {
        const existing = messages.find((m) => m.idempotencyKey === input.idempotencyKey)
        if (existing) return existing
      }
      const message: StoredMessage = {
        id: input.messageId,
        conversationId: input.conversationId,
        role: input.role,
        content: input.content,
        triggerSource: input.triggerSource,
        idempotencyKey: input.idempotencyKey,
        createdAt: input.createdAt,
      }
      messages.push(message)
      return message
    },

    async getRun(runId) {
      return runs.get(runId) ?? null
    },

    async findActiveMainRun(conversationId) {
      const active = [...runs.values()]
        .filter(
          (r) =>
            r.conversationId === conversationId &&
            r.parentRunId === null &&
            ACTIVE_MAIN_RUN_STATUSES.includes(r.status),
        )
        .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())
      return active[0] ?? null
    },

    async getStep(stepId) {
      return steps.get(stepId) ?? null
    },

    async updateStep({ stepId, status, output, updatedAt }) {
      const step = steps.get(stepId)
      if (!step) throw new Error(`step not found: ${stepId}`)
      const next: StoredStep = {
        ...step,
        status: status === undefined ? step.status : status,
        output: output === undefined ? step.output : output,
        updatedAt,
      }
      steps.set(stepId, next)
      return next
    },

    async listWaitingApprovalSteps() {
      // S-C parity: production only treats kind==='approval' && status==='waiting' steps
      // as "waiting for approval", ordered by createdAt asc.
      return [...steps.values()]
        .filter((s) => s.kind === "approval" && s.status === "waiting")
        .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime())
    },

    async listWaitingApprovalStepsForConversation(conversationId) {
      // S-C parity: same kind==='approval' gate + createdAt asc order, scoped to conversation.
      return [...steps.values()]
        .filter(
          (s) =>
            s.kind === "approval" &&
            s.status === "waiting" &&
            runs.get(s.runId)?.conversationId === conversationId,
        )
        .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime())
    },

    async createScopedGrant(input) {
      const record: ScopedGrantRecord = {
        id: input.grantId,
        runId: input.runId,
        subject: input.subject,
        capability: input.capability,
        scope: input.scope,
        remainingUses: input.remainingUses,
        expiresAtMs: input.expiresAt.getTime(),
        createdAtMs: input.createdAt.getTime(),
        delegable: input.delegable ?? false,
        approvalId: input.approvalId ?? null,
        sandboxProfile: input.sandboxProfile ?? null,
        networkAllowlist: input.networkAllowlist ?? null,
      }
      grants.set(record.id, record)
      return record
    },

    async findActiveGrant({ runId, subject, capability, digest, now }) {
      const matches = [...grants.values()].filter(
        (g) =>
          g.runId === runId &&
          g.subject === subject &&
          g.capability === capability &&
          g.expiresAtMs > now.getTime() &&
          (g.remainingUses === null || g.remainingUses > 0) &&
          // S-F parity: a grant WITHOUT scope.digest accepts any digest (production
          // grantMatchesAction only gates when the grant itself pins a digest).
          (digest === undefined ||
            g.scope.digest === undefined ||
            g.scope.digest === digest),
      )
      return matches[0] ?? null
    },

    async appendAuditEvent(input) {
      appendAudit(input as AuditEventRecord)
    },

    async updateScopedGrantRemainingUses(grantId, remainingUses) {
      const grant = grants.get(grantId)
      if (grant) grants.set(grantId, { ...grant, remainingUses })
    },

    async revokeScopedGrantsForMcpServer(serverId, now) {
      let count = 0
      for (const [id, g] of grants) {
        if (g.scope.mcp?.serverId === serverId && g.expiresAtMs > now.getTime()) {
          grants.set(id, { ...g, remainingUses: 0 })
          count++
        }
      }
      return count
    },

    async countActiveScopedGrantsForMcpServer(serverId, now) {
      return [...grants.values()].filter(
        (g) =>
          g.scope.mcp?.serverId === serverId &&
          g.expiresAtMs > now.getTime() &&
          (g.remainingUses === null || g.remainingUses > 0),
      ).length
    },

    async revokeScopedGrantsForCapability(capability, now) {
      let count = 0
      for (const [id, g] of grants) {
        if (g.capability === capability && g.expiresAtMs > now.getTime()) {
          grants.set(id, { ...g, remainingUses: 0 })
          count++
        }
      }
      return count
    },

    async listRunsPastDeadline(now) {
      const t = now.getTime()
      // S-D parity: production only re-sweeps non-terminal Runs past the deadline
      // (ACTIVE_MAIN_RUN_STATUSES), ordered by deadline asc. Terminal runs are never
      // swept back into the deadline path.
      return [...runs.values()]
        .filter(
          (r) =>
            r.deadline !== null &&
            r.deadline.getTime() < t &&
            ACTIVE_MAIN_RUN_STATUSES.includes(r.status),
        )
        .sort((a, b) => (a.deadline as Date).getTime() - (b.deadline as Date).getTime())
    },

    async findChildRuns(parentRunId) {
      // S-E parity: production returns child Runs by createdAt desc (most recent first)
      // so downstream (cancelRun cascade) can process in a stable order.
      return [...runs.values()]
        .filter((r) => r.parentRunId === parentRunId)
        .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())
    },

    async appendAuditEventInTx(_tx, input) {
      appendAudit(input)
    },

    async transitionRunStatusInTx(_tx, runId, expectedVersion, to, updatedAt) {
      return transitionRunStatus(runId, expectedVersion, to, updatedAt)
    },

    withTransaction,
  }
}