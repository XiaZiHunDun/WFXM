import { describe, expect, it } from "vitest"
import type { AuditEntry } from "./audit-log.js"
import {
  findCompletedDuplicateInAudit,
  formatDuplicateRejection,
  isDelegationDedupeEnabled,
  normalizeTaskText,
  resolveDedupeThreshold,
  taskSimilarity,
} from "./delegation-dedupe.js"

function entry(partial: Partial<AuditEntry> & Pick<AuditEntry, "kind">): AuditEntry {
  return {
    ts: "2026-11-27T04:00:00.000Z",
    parentConversationId: "c-owner",
    childConversationId: "child-1",
    role: "developer",
    task: "",
    capabilities: ["write_file"],
    ...partial,
  }
}

const SHELF_SORT_TASK =
  "在 LingWen 加书架排序：listBooks 支持 updated/created/title/words，书卡显示最近编辑时间与字数，新增 tests/book-sort.test.mjs"

describe("delegation-dedupe", () => {
  it("normalizes whitespace and bounds length", () => {
    expect(normalizeTaskText("  a \n b\tc  ")).toBe("a b c")
    expect(normalizeTaskText("x".repeat(2000)).length).toBe(600)
  })

  it("scores identical / near-identical tasks close to 1", () => {
    expect(taskSimilarity(SHELF_SORT_TASK, SHELF_SORT_TASK)).toBe(1)
    const replayed = `${SHELF_SORT_TASK}。`
    expect(taskSimilarity(SHELF_SORT_TASK, replayed)).toBeGreaterThan(0.95)
    expect(taskSimilarity(SHELF_SORT_TASK, "给工作台加命令面板")).toBeLessThan(0.45)
  })

  it("matches the real batch-V replay wording (same feature, reworded)", () => {
    const original =
      "在 LingWen 仓库（/home/ailearn/projects/LingWen）实现「书架排序 + 最近编辑时间」。仅改本仓库源码，改文件必须用 edit_file/write_file，禁止用 run_command 内联脚本改文件。要求：listBooks 支持 updated/created/title/words，书卡显示最近编辑时间与字数，新增 tests/book-sort.test.mjs。"
    const reworded =
      "在 LingWen（工作区根即 Next 应用：src/app、src/lib、tests）实现「书架排序 + 最近编辑时间」。硬性约束：只改本仓库源码；改文件必须用 edit_file/write_file，禁止内联脚本改文件。要求：listBooks 支持 updated/created/title/words 四档，书卡显示最近编辑时间与字数，新增 tests/book-sort.test.mjs。"
    expect(taskSimilarity(original, reworded)).toBeGreaterThanOrEqual(0.45)
  })

  it("env toggles and threshold defaults", () => {
    expect(isDelegationDedupeEnabled({})).toBe(true)
    expect(isDelegationDedupeEnabled({ BUTLER_V5_DELEGATION_DEDUPE: "0" })).toBe(false)
    expect(resolveDedupeThreshold({})).toBe(0.45)
    expect(resolveDedupeThreshold({ BUTLER_V5_DELEGATION_DEDUPE_THRESHOLD: "0.6" })).toBe(0.6)
    expect(resolveDedupeThreshold({ BUTLER_V5_DELEGATION_DEDUPE_THRESHOLD: "3" })).toBe(0.95)
    expect(resolveDedupeThreshold({ BUTLER_V5_DELEGATION_DEDUPE_THRESHOLD: "abc" })).toBe(0.45)
  })

  it("detects a replayed task that already completed in the same conversation", () => {
    const entries: AuditEntry[] = [
      entry({ kind: "delegation", task: SHELF_SORT_TASK, childConversationId: "child-1" }),
      entry({ kind: "completion", task: SHELF_SORT_TASK, childConversationId: "child-1" }),
    ]
    const dup = findCompletedDuplicateInAudit({
      task: SHELF_SORT_TASK,
      parentConversationId: "c-owner",
      entries,
    })
    expect(dup?.childConversationId).toBe("child-1")
    expect(dup?.similarity).toBe(1)
  })

  it("ignores tasks that never completed, or that belong to another conversation", () => {
    const pending: AuditEntry[] = [
      entry({ kind: "delegation", task: SHELF_SORT_TASK, childConversationId: "child-1" }),
    ]
    expect(
      findCompletedDuplicateInAudit({
        task: SHELF_SORT_TASK,
        parentConversationId: "c-owner",
        entries: pending,
      }),
    ).toBeUndefined()

    const otherConversation: AuditEntry[] = [
      entry({
        kind: "delegation",
        task: SHELF_SORT_TASK,
        childConversationId: "child-2",
        parentConversationId: "c-other",
      }),
      entry({
        kind: "completion",
        task: SHELF_SORT_TASK,
        childConversationId: "child-2",
        parentConversationId: "c-other",
      }),
    ]
    expect(
      findCompletedDuplicateInAudit({
        task: SHELF_SORT_TASK,
        parentConversationId: "c-owner",
        entries: otherConversation,
      }),
    ).toBeUndefined()
  })

  it("lets explicit rework intent through", () => {
    const entries: AuditEntry[] = [
      entry({ kind: "delegation", task: SHELF_SORT_TASK }),
      entry({ kind: "completion", task: SHELF_SORT_TASK }),
    ]
    expect(
      findCompletedDuplicateInAudit({
        task: `返工：${SHELF_SORT_TASK}`,
        parentConversationId: "c-owner",
        entries,
      }),
    ).toBeUndefined()
  })

  it("ignores completions outside the 24h window and very short tasks", () => {
    const old: AuditEntry[] = [
      entry({ kind: "delegation", task: SHELF_SORT_TASK, ts: "2026-11-20T00:00:00.000Z" }),
      entry({ kind: "completion", task: SHELF_SORT_TASK, ts: "2026-11-20T00:00:00.000Z" }),
    ]
    expect(
      findCompletedDuplicateInAudit({
        task: SHELF_SORT_TASK,
        parentConversationId: "c-owner",
        entries: old,
        nowMs: Date.parse("2026-11-27T04:00:00.000Z"),
      }),
    ).toBeUndefined()
    expect(
      findCompletedDuplicateInAudit({
        task: "改个词",
        parentConversationId: "c-owner",
        entries: [
          entry({ kind: "delegation", task: "改个词" }),
          entry({ kind: "completion", task: "改个词" }),
        ],
      }),
    ).toBeUndefined()
  })

  it("respects the env kill switch", () => {
    const entries: AuditEntry[] = [
      entry({ kind: "delegation", task: SHELF_SORT_TASK }),
      entry({ kind: "completion", task: SHELF_SORT_TASK }),
    ]
    expect(
      findCompletedDuplicateInAudit({
        task: SHELF_SORT_TASK,
        parentConversationId: "c-owner",
        entries,
        env: { BUTLER_V5_DELEGATION_DEDUPE: "0" },
      }),
    ).toBeUndefined()
  })

  it("formats an owner-facing rejection with the percentage and an escape hatch", () => {
    const text = formatDuplicateRejection({
      task: SHELF_SORT_TASK,
      childConversationId: "child-1",
      similarity: 0.97,
      completedAt: "2026-11-27T04:00:00.000Z",
    })
    expect(text).toContain("97%")
    expect(text).toContain("不要原样重发")
    expect(text).toContain("修复/返工")
  })
})
