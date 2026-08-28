/**
 * Outbox Port — Core 依赖的 outbox 抽象（DESIGN §11.3）。
 *
 * Outbox 解决状态提交与异步副作用（外部 Channel 发送、Child Run 派发、
 * 事务后通知）的一致性。仅承载事务提交后的异步副作用（DESIGN §11.3），
 * 不作为通用领域事件总线。仅依赖内建类型（DESIGN §7 / §17）。
 *
 * 生产实现由 `packages/adapters/src/postgres/postgres-outbox.ts` 提供；
 * 本文件提供 `memoryOutbox()` 开发/测试用内存实现。
 */

export interface OutboxEnqueueInput {
  readonly streamId: string
  readonly aggregateType: string
  readonly payload: Record<string, unknown>
}

export interface OutboxMessage {
  readonly messageId: string
  readonly streamId: string
  readonly aggregateType: string
  readonly payload: Record<string, unknown>
}

export interface OutboxPort {
  /** 入队。事务提交后调用；返回新消息 id。 */
  readonly enqueue: (
    input: OutboxEnqueueInput,
  ) => Promise<{ readonly messageId: string }>

  /** 拉取一批可处理消息（默认上限 10 条）；仅返回未 complete/fail 的。 */
  readonly claim: () => Promise<readonly OutboxMessage[]>

  /** 标记消息完成。后续 claim 不再返回。 */
  readonly complete: (messageId: string) => Promise<void>

  /** 标记消息失败（永久 / 不可恢复错误）。后续 claim 不再返回。 */
  readonly fail: (messageId: string, error: string) => Promise<void>

  /** 运行一轮 worker：循环 claim → handler → complete/fail，返回处理条数。 */
  readonly runWorker: (
    handler: (msg: OutboxMessage) => Promise<void>,
  ) => Promise<number>
}

/** 内存 outbox：开发/测试用；不持久化、lease 不强制。 */
export function memoryOutbox(): OutboxPort {
  type Row = {
    readonly messageId: string
    readonly streamId: string
    readonly aggregateType: string
    readonly payload: Record<string, unknown>
    state: "pending" | "completed" | "failed"
  }
  let nextId = 0
  const rows: Row[] = []

  const port: OutboxPort = {
    enqueue: async (input) => {
      const messageId = `mem-${++nextId}`
      rows.push({
        messageId,
        streamId: input.streamId,
        aggregateType: input.aggregateType,
        payload: input.payload,
        state: "pending",
      })
      return { messageId }
    },
    claim: async () => {
      return rows
        .filter((r) => r.state === "pending")
        .slice(0, 10)
        .map((r) => ({
          messageId: r.messageId,
          streamId: r.streamId,
          aggregateType: r.aggregateType,
          payload: r.payload,
        }))
    },
    complete: async (messageId) => {
      const row = rows.find((r) => r.messageId === messageId)
      if (row) row.state = "completed"
    },
    fail: async (messageId) => {
      const row = rows.find((r) => r.messageId === messageId)
      if (row) row.state = "failed"
    },
    runWorker: async (handler) => {
      let processed = 0
      // 内联 claim 逻辑（不能用 `this.claim()` 引用 port）
      for (;;) {
        const claimed = rows
          .filter((r) => r.state === "pending")
          .slice(0, 10)
          .map((r) => ({
            messageId: r.messageId,
            streamId: r.streamId,
            aggregateType: r.aggregateType,
            payload: r.payload,
          }))
        if (claimed.length === 0) break
        for (const msg of claimed) {
          try {
            await handler(msg)
            const row = rows.find((r) => r.messageId === msg.messageId)
            if (row) row.state = "completed"
            processed++
          } catch (err) {
            const row = rows.find((r) => r.messageId === msg.messageId)
            if (row) row.state = "failed"
            throw err
          }
        }
      }
      return processed
    },
  }
  return port
}
