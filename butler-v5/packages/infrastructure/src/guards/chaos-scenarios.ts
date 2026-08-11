// infrastructure/guards/chaos-scenarios.ts
// 混沌演练场景 [G-10] — 5 个精简场景
// Phase 4 实现

import type { LoopError, GuardFinding } from "@butler/domain"

// ─── 混沌场景定义 ───────────────────────────────────────
export type ChaosScenario = {
  readonly name: string
  readonly description: string
  readonly inject: () => LoopError
  readonly expectedGuard: string
  readonly expectedFinding: GuardFinding
}

export const chaosScenarios: readonly ChaosScenario[] = [
  {
    name: "fake-completion",
    description: "AI 虚假完成（无证据文件）",
    inject: () => ({
      _tag: "GuardRejected" as const,
      reason: { _tag: "MissingEvidence" as const },
    }),
    expectedGuard: "G-1",
    expectedFinding: {
      guard: "intent-receipt",
      status: "fail",
      detail: "No evidence files provided",
    },
  },
  {
    name: "owner-offline-write",
    description: "Owner 离线时写操作被拒绝",
    inject: () => ({
      _tag: "GuardRejected" as const,
      reason: { _tag: "OwnerOffline" as const, action: "write_file" },
    }),
    expectedGuard: "G-3",
    expectedFinding: {
      guard: "owner-offline-policy",
      status: "fail",
      detail: "Owner offline, write blocked",
    },
  },
  {
    name: "load-bearing-delete",
    description: "删除承重代码被拒绝",
    inject: () => ({
      _tag: "GuardRejected" as const,
      reason: { _tag: "LoadBearingTouched" as const, path: "src/loop.ts" },
    }),
    expectedGuard: "G-2",
    expectedFinding: {
      guard: "load-bearing",
      status: "fail",
      detail: "Load-bearing code touched",
    },
  },
  {
    name: "role-conflict",
    description: "Author 与 Reviewer 相同",
    inject: () => ({
      _tag: "GuardRejected" as const,
      reason: {
        _tag: "RoleConflict" as const,
        author: "claude-3-5-sonnet",
        reviewer: "claude-3-5-sonnet",
      },
    }),
    expectedGuard: "G-7",
    expectedFinding: {
      guard: "role-separation",
      status: "fail",
      detail: "Author cannot review own work",
    },
  },
  {
    name: "chain-incomplete",
    description: "多文件链路缺失",
    inject: () => ({
      _tag: "GuardRejected" as const,
      reason: {
        _tag: "ChainIncomplete" as const,
        missing: ["src/App.test.tsx"],
      },
    }),
    expectedGuard: "G-5",
    expectedFinding: {
      guard: "multi-file-chain",
      status: "fail",
      detail: "Chain incomplete",
    },
  },
]

// ─── 混沌演练执行器 ─────────────────────────────────────
export function runChaosDrill(scenario: ChaosScenario): {
  passed: boolean
  guard: string
  error: LoopError
} {
  const error = scenario.inject()
  return {
    passed: error._tag === "GuardRejected",
    guard: scenario.expectedGuard,
    error,
  }
}
