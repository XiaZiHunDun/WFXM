import { describe, expect, it } from "vitest"
import type { ButlerTaskRef } from "@butler/ports/core/butler-task.js"
import { buildApprovalNotice, parseApprovalPayload } from "./approval-notice.js"

const paused: ButlerTaskRef = {
  taskId: "task-1",
  projectId: "p1",
  status: "paused",
  summary: "修复登录超时",
  pending: { toolName: "write", reason: "需要审批", requestedAt: "2026-11-17T10:00:00Z" },
}

describe("buildApprovalNotice", () => {
  it("renders text and card actions for a paused task", () => {
    const notice = buildApprovalNotice(paused)
    expect(notice?.title).toBe("任务 task-1 需要确认")
    expect(notice?.text).toContain("目标：修复登录超时")
    expect(notice?.text).toContain("待执行：修改文件")
    expect(notice?.text).toContain("回复「确认」继续")
    expect(notice?.actions.map((action) => action.payload)).toEqual([
      "approve:task-1",
      "reject:task-1",
    ])
    expect(notice?.actions[0]?.label).toBe("确认")
  })

  it("returns null unless the task is paused with a pending step", () => {
    expect(buildApprovalNotice({ ...paused, status: "idle" })).toBeNull()
    expect(buildApprovalNotice({ ...paused, pending: undefined })).toBeNull()
  })
})

describe("parseApprovalPayload", () => {
  it("parses card payloads", () => {
    expect(parseApprovalPayload({ payload: "approve:task-1" })).toEqual({
      taskId: "task-1",
      approved: true,
    })
    expect(parseApprovalPayload({ payload: "reject:task-1" })).toEqual({
      taskId: "task-1",
      approved: false,
    })
  })

  it("falls back to a bare action plus the active task", () => {
    expect(parseApprovalPayload({ action: "approve", activeTaskId: "t1" })).toEqual({
      taskId: "t1",
      approved: true,
    })
    expect(parseApprovalPayload({ action: "reject" })).toBeNull()
    expect(parseApprovalPayload({ payload: "confirm:t1" })).toBeNull()
    expect(parseApprovalPayload({})).toBeNull()
  })
})
