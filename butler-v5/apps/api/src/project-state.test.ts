import { describe, expect, it } from "vitest"
import { mkdtempSync, rmSync } from "node:fs"
import { join } from "node:path"
import { tmpdir } from "node:os"
import {
  childRunStatusLabel,
  formatProjectStateLines,
  getProjectState,
  recordChildRunDelegated,
  recordChildRunStatus,
  updateProjectState,
} from "./project-state.js"

describe("project-state", () => {
  it("formats child run and verify lines", () => {
    const lines = formatProjectStateLines({
      branch: "main",
      wipSummary: "fix login",
      lastChildRunId: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      lastChildRunStatus: "running",
      lastChildRunRole: "developer",
      lastChildRunTask: "write tmp.txt",
      lastVerifyOk: true,
      lastVerifyCommand: "pnpm test",
      lastVerifyExitCode: 0,
      lastVerifyAtMs: Date.now(),
    })
    expect(lines.some((l) => l.includes("子代理：developer · 执行中"))).toBe(true)
    expect(lines.some((l) => l.includes("子代理任务：write tmp.txt"))).toBe(true)
    expect(lines.some((l) => l.includes("末次验收：✓"))).toBe(true)
  })

  it("records delegate then status transitions", () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-pstate-cr-"))
    const env = { BUTLER_V5_PROJECT_STATE_STORE: join(dir, "state.json") }
    try {
      recordChildRunDelegated({
        userId: "u1",
        projectId: "wechat",
        childRunId: "run-11111111-2222-3333-4444-555555555555",
        role: "developer",
        task: "implement cache",
        env,
      })
      let state = getProjectState({ userId: "u1", projectId: "wechat", env })
      expect(state?.lastChildRunStatus).toBe("queued")
      expect(state?.lastChildRunTask).toBe("implement cache")

      recordChildRunStatus({
        userId: "u1",
        projectId: "wechat",
        childRunId: "run-11111111-2222-3333-4444-555555555555",
        status: "running",
        env,
      })
      state = getProjectState({ userId: "u1", projectId: "wechat", env })
      expect(state?.lastChildRunStatus).toBe("running")
      expect(childRunStatusLabel(state?.lastChildRunStatus)).toBe("执行中")

      recordChildRunStatus({
        userId: "u1",
        projectId: "wechat",
        childRunId: "run-11111111-2222-3333-4444-555555555555",
        status: "succeeded",
        env,
      })
      state = getProjectState({ userId: "u1", projectId: "wechat", env })
      expect(state?.lastChildRunStatus).toBe("succeeded")

      recordChildRunDelegated({
        userId: "u1",
        projectId: "wechat",
        childRunId: "run-99999999-8888-7777-6666-555555555555",
        role: "developer",
        task: "new task",
        env,
      })
      const stale = recordChildRunStatus({
        userId: "u1",
        projectId: "wechat",
        childRunId: "run-11111111-2222-3333-4444-555555555555",
        status: "failed",
        env,
      })
      expect(stale).toBeNull()
      state = getProjectState({ userId: "u1", projectId: "wechat", env })
      expect(state?.lastChildRunId).toContain("99999999")
      expect(state?.lastChildRunStatus).toBe("queued")
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it("persists per user/project state", () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-v5-pstate-"))
    const env = { BUTLER_V5_PROJECT_STATE_STORE: join(dir, "state.json") }
    try {
      updateProjectState({
        userId: "u1",
        projectId: "wechat",
        patch: { wipSummary: "实现 write_file", branch: "main" },
        env,
      })
      const state = getProjectState({ userId: "u1", projectId: "wechat", env })
      expect(state?.wipSummary).toBe("实现 write_file")
      expect(state?.branch).toBe("main")
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  })
})
