import { describe, it, expect } from "vitest"
import type { LoopError, GuardReason } from "./errors.js"
import { toFixSuggestion } from "./errors.js"

describe("domain/errors", () => {
  it("LoopError types are valid", () => {
    const err: LoopError = {
      _tag: "LLMUnavailable",
      provider: "anthropic",
    }
    expect(err._tag).toBe("LLMUnavailable")
    expect(err.provider).toBe("anthropic")
  })

  it("GuardReason sub-types are valid", () => {
    const reason: GuardReason = {
      _tag: "MissingEvidence",
    }
    expect(reason._tag).toBe("MissingEvidence")
  })

  it("GuardRejected wraps a GuardReason", () => {
    const err: LoopError = {
      _tag: "GuardRejected",
      reason: { _tag: "LoadBearingTouched", path: "src/loop.ts" },
    }
    expect(err._tag).toBe("GuardRejected")
    if (err._tag === "GuardRejected") {
      expect(err.reason._tag).toBe("LoadBearingTouched")
    }
  })
})

describe("toFixSuggestion", () => {
  it("explains each leaf-error variant", () => {
    expect(toFixSuggestion({ _tag: "LLMUnavailable", provider: "openai" })).toBe(
      "Provider openai 不可用，已触发 Retry/Fallback（[G-8]），如仍失败将通知 Owner",
    )
    expect(toFixSuggestion({ _tag: "ContextOverflow", tokens: 128000 })).toBe(
      "上下文超限（128000 tokens），请压缩或拆分任务",
    )
    expect(toFixSuggestion({ _tag: "ToolFailed", toolId: "run_command", cause: "exit 1" })).toBe(
      "工具 run_command 执行失败：exit 1",
    )
    expect(toFixSuggestion({ _tag: "OwnerOfflineTimeout", since: 60000 })).toBe(
      "Owner 离线超时（60000ms），任务已暂停",
    )
    expect(toFixSuggestion({ _tag: "PersistenceFailed", operation: "upsert_run", cause: "db down" })).toBe(
      "持久化操作 upsert_run 失败：db down",
    )
  })

  it("unwraps nested workflow failures recursively", () => {
    expect(
      toFixSuggestion({
        _tag: "WorkflowFailed",
        workflowId: "build",
        cause: { _tag: "ToolFailed", toolId: "compile", cause: "type error" },
      }),
    ).toBe("工作流 build 失败，原因：工具 compile 执行失败：type error")
  })

  it("reports each guard-rejection reason [G-1..G-10]", () => {
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "MissingEvidence" } })).toBe(
      "缺少 IntentReceipt，请补充 evidenceFiles [G-1]",
    )
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "LoadBearingTouched", path: "core/loop.py" } })).toContain(
      "core/loop.py",
    )
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "OwnerOffline", action: "write_file" } })).toContain(
      "write_file",
    )
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "InvalidHumanSig", field: "ownerSig" } })).toContain(
      "ownerSig",
    )
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "ChainIncomplete", missing: ["a.ts", "b.ts"] } })).toBe(
      "多文件链路缺失：a.ts, b.ts [G-5]",
    )
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "VerificationLevelNotMet", required: "Standard" } })).toBe(
      "需要 Standard 级验证 [G-6]",
    )
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "RoleConflict", author: "me", reviewer: "me" } })).toContain(
      "me",
    )
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "HealFailed", layer: "fallback" } })).toContain(
      "fallback",
    )
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "AntiPatternDetected", pattern: "pony" } })).toBe(
      "检测到反模式：pony [G-9]",
    )
    expect(toFixSuggestion({ _tag: "GuardRejected", reason: { _tag: "ChaosFailure", scenario: "net-partition" } })).toBe(
      "混沌演练失败：net-partition [G-10]",
    )
  })
})
