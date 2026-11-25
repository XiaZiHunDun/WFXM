import { describe, expect, it } from "vitest"
import { createTraceEvent, type TraceEvent } from "@butler/domain/observability/local-trace.js"
import { clusterFailures, clusterKey, renderFailureClusters } from "./failure-clusters.js"

function failure(detail: Record<string, unknown> = {}): TraceEvent {
  return createTraceEvent({ kind: "run", name: "finish", status: "error", detail })
}

describe("clusterFailures", () => {
  it("groups failures by code × tool and sorts by count", () => {
    const summary = clusterFailures([
      failure({ code: "E-LLM-01", tool: "write_file" }),
      failure({ code: "E-LLM-01", tool: "write_file" }),
      failure({ code: "E-TOOL-02", tool: "run_command" }),
      createTraceEvent({ kind: "run", name: "finish", status: "ok" }),
    ])
    expect(summary.total).toBe(3)
    expect(summary.clusters).toEqual([
      { key: "E-LLM-01 × write_file", count: 2 },
      { key: "E-TOOL-02 × run_command", count: 1 },
    ])
  })

  it("falls back when code / tool are missing", () => {
    expect(clusterKey(failure())).toBe("未标注错误码 × 无工具")
    expect(clusterKey(failure({ code: "E-1" }))).toBe("E-1 × 无工具")
  })

  it("counts the legacy run_failed shape and caps output", () => {
    const events = Array.from({ length: 9 }, (_, i) =>
      createTraceEvent({ kind: "step", name: "run_failed", detail: { code: `E-${i}` } }),
    )
    const summary = clusterFailures(events, 3)
    expect(summary.total).toBe(9)
    expect(summary.clusters).toHaveLength(3)
  })

  it("renders nothing when there are no failures", () => {
    expect(renderFailureClusters({ total: 0, clusters: [] })).toBeNull()
    expect(renderFailureClusters({ total: 2, clusters: [{ key: "E-1 × 无工具", count: 2 }] })).toBe(
      "失败聚类：E-1 × 无工具（2）",
    )
  })
})
