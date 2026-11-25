/**
 * Phase 6 P1: turn raw failure traces into owner-readable clusters.
 *
 * The analysis stage used to stop at "失败 N 次". Grouping by
 * `error code × tool` is the smallest step that answers "失败在哪里",
 * and it feeds both `/诊断` and the weekly digest from the same rows.
 */
import type { TraceEvent } from "@butler/domain/observability/local-trace.js"
import { isFailedRunTrace } from "@butler/domain/observability/local-trace.js"

export interface FailureCluster {
  readonly key: string
  readonly count: number
}

export interface FailureSummary {
  readonly total: number
  readonly clusters: readonly FailureCluster[]
}

function detailString(event: TraceEvent, key: string): string | null {
  const value = (event.detail ?? {})[key]
  return typeof value === "string" && value.length > 0 ? value : null
}

export function clusterKey(event: TraceEvent): string {
  const code = detailString(event, "code") ?? "未标注错误码"
  const tool = detailString(event, "tool") ?? detailString(event, "name") ?? "无工具"
  return `${code} × ${tool}`
}

export function clusterFailures(events: readonly TraceEvent[], limit: number = 5): FailureSummary {
  const counts = new Map<string, number>()
  let total = 0
  for (const event of events) {
    if (!isFailedRunTrace(event)) continue
    total += 1
    const key = clusterKey(event)
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  const clusters = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, Math.max(1, limit))
    .map(([key, count]) => ({ key, count }))
  return { total, clusters }
}

/** One owner-facing line, or null when there is nothing to show. */
export function renderFailureClusters(summary: FailureSummary): string | null {
  if (summary.total === 0 || summary.clusters.length === 0) return null
  const parts = summary.clusters.map((cluster) => `${cluster.key}（${cluster.count}）`)
  return `失败聚类：${parts.join("、")}`
}
