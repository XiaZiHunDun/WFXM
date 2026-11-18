/**
 * Projection Port — Core 依赖的读模型抽象。
 *
 * Projection 把事件流投影到读模型（视图）。仅依赖内建类型
 * （DESIGN §7 / §17）。
 *
 * 注：projection handler 的具体签名由底层持久层（postgres / pglite）
 * 定义，本端口使用宽松类型接受任何兼容 handler。
 *
 * 生产实现由 `packages/adapters/src/postgres/postgres-projection.ts` 提供；
 * 本文件提供 `memoryProjection()` 开发/测试用。
 */

export type ProjectionHandler = (...args: readonly unknown[]) => unknown

export interface ProjectionPort {
  /** 应用流上的未处理事件到指定 projection。 */
  readonly apply: (streamId: string, name: string) => Promise<void>

  /** 从头重建 projection（用于 schema 变化后的回填）。 */
  readonly rebuild: (streamId: string, name: string) => Promise<void>

  /** 注册 projection handler。 */
  readonly register: (name: string, handler: ProjectionHandler) => Promise<void>
}

/** 内存 projection：开发/测试用，handlers 缓存在 Map（不自动调用）。 */
export function memoryProjection(): ProjectionPort {
  const handlers = new Map<string, ProjectionHandler>()
  return {
    apply: async (_streamId, _name) => {
      // 内存实现跳过事件应用（无事件源）
    },
    rebuild: async (_streamId, _name) => {
      // 内存实现跳过重建（无事件源）
    },
    register: async (name, handler) => {
      handlers.set(name, handler)
    },
  }
}
