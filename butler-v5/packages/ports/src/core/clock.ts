/**
 * Clock Port — Core 依赖的可注入时钟抽象（DESIGN §7）。
 *
 * Application 编排层用该接口生成业务时间戳（createdAt、状态时间、deadline /
 * expires），以便确定性测试与替换（可注入假时钟）。纯观测计时（如 trace
 * durationMs）不强制走该接口。实现由 Composition Root 注入，生产用
 * `systemClock`，测试可注入 `fixedClock`。
 *
 * 仅依赖 domain 类型（实际为内建 Date，零依赖），DESIGN §7 / §17。
 */
export interface ClockPort {
  /** 当前业务时间。 */
  readonly now: () => Date
}

/** 系统时钟（生产默认实现）——组合根注入。 */
export const systemClock: ClockPort = {
  now: () => new Date(),
}

/** 固定时钟（测试/示例用）：`now()` 始终返回同一时刻。 */
export function fixedClock(at: Date): ClockPort {
  return { now: () => at }
}