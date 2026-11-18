/**
 * Snapshot Port — Core 依赖的 per-stream 状态快照抽象。
 *
 * Application 用该接口保存/加载当前状态快照，避免重启后全量重放。
 * 仅依赖内建类型（DESIGN §7 / §17）。
 *
 * 生产实现由 `packages/adapters/src/postgres/postgres-snapshot.ts` 提供；
 * 本文件提供 `memorySnapshot()` 开发/测试用。
 */

export interface SnapshotRecord {
  readonly streamVersion: number
  readonly payload: Record<string, unknown>
}

export interface SnapshotPort {
  /** 加载快照。无快照时返回 null。 */
  readonly load: (streamId: string) => Promise<SnapshotRecord | null>

  /** 保存快照。生产实现应在 streamVersion 冲突时抛错。 */
  readonly save: (
    streamId: string,
    streamVersion: number,
    payload: Record<string, unknown>,
  ) => Promise<void>
}

/** 内存 snapshot：开发/测试用。 */
export function memorySnapshot(): SnapshotPort {
  const store = new Map<string, SnapshotRecord>()
  return {
    load: async (streamId) => store.get(streamId) ?? null,
    save: async (streamId, streamVersion, payload) => {
      store.set(streamId, { streamVersion, payload })
    },
  }
}
