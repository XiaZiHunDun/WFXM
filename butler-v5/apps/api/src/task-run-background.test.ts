import { describe, expect, it } from "vitest"
import { isTaskRunAsyncEnabled } from "./task-run-background.js"
import { formatTaskRunCompletionNotify } from "./wechat-run-notify.js"

describe("task-run-background", () => {
  it("isTaskRunAsyncEnabled when run notify or async flag is on", () => {
    expect(isTaskRunAsyncEnabled({})).toBe(false)
    expect(isTaskRunAsyncEnabled({ BUTLER_V5_TASK_RUN_ASYNC: "1" })).toBe(true)
    expect(isTaskRunAsyncEnabled({ BUTLER_V5_RUN_NOTIFY_ENABLED: "1" })).toBe(true)
  })

  it("formatTaskRunCompletionNotify includes task id and decision", () => {
    const text = formatTaskRunCompletionNotify({
      taskId: "abcd1234-efgh",
      title: "修 smoke",
      decision: "Respond",
      reply: "done",
      ok: true,
    })
    expect(text).toContain("【待办完成】")
    expect(text).toContain("abcd1234")
    expect(text).toContain("Respond")
  })
})
