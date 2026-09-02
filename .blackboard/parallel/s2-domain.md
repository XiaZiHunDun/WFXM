# S2 — domain 会话（契约/类型/状态机 上游）

**职责**：负责 `packages/domain/**`——纯类型、契约（如 `RuntimeStore` 接口）、状态转换（`transitions`/`run-trigger`）、治理类型（`governance`）。全仓最上游，最少冲突，最易并行。

## 独占路径

- `packages/domain/**`

## 边界（不可动）

- 任何 `@butler/ports|persistence|runtime|adapters|apps` 之外的包都不得 import 进 domain（防环；domain 只能 import 标准库/Typescript 自身与同包内部）。
- 不改 ports barrel / DESIGN.md / port-catalog.md（归 S1）。
- 若需新增 domain 契约子路径供他包消费：D1 改 `packages/domain/package.json` 的 `exports`——**该文件属 S1 终审**，提 PR 由 S1 落。

## 依赖/上游

- 无下游消费方约束；改契约签名会波及 S3/S4/S5/S6，**签名变更前先发 `@` note 给对应会话**，或在 PR 描述里 @S1 让其在合并时统一协调。

## 常规先手

- 契约稳定优先：新增接口/类型导出走 `store-contract.ts` 或领域子包，产出被 S3/S4/S5 引用。
- 复读 `butler-v5/DESIGN.md`（概念/数据/扩展边界）再改。

## 最小门禁（提交前）

```bash
cd butler-v5/packages/domain && pnpm exec tsc --noEmit
cd butler-v5 && CI= pnpm exec vitest run packages/domain -q
pnpm exec eslint packages/domain --ext .ts --max-warnings 0
```

## 当前相关待办

- 多为被动：S3/S4/S5 暴露端口/持久化需求时，为其收敛/新增 domain 契约。无独占待办候选（D47 特征不落 domain）。

> ⚠️  **历史待办**：以下 Wave-3 任务已在 M2（main `4a6e628f`）全部收口完成，本段仅作归档留底。
>  ✅ 实际完成见末尾「M2 收口摘要」。

## Wave-3 主项：SSOT `isTerminalRunStatus`（S2+S1 协调，2026-09-02 立项）

- **现状**：`packages/domain/src/runtime/transitions.ts` 有 `LEGAL_TRANSITIONS`（无出边即 terminal），但**未导出** terminal 判断；runtime 侧 `run-lifecycle.ts` 自维护本地 `TERMINAL_RUN_STATUSES`（重复定义）。
- **任务**：在 `transitions.ts` 新增导出 `isTerminalRunStatus(status): boolean`（由 `LEGAL_TRANSITIONS[status].length === 0` 推导，避免硬编码重复）＋ `TERMINAL_RUN_STATUSES` 常量（从 `LEGAL_TRANSITIONS` 无出边状态派生）；经 barrel `runtime/index.ts` 导出。
- **测试**：`transitions.test.ts` 已定义 `TERMINAL_STATUSES`（succeeded/failed/cancelled/expired），补 `isTerminalRunStatus` 正反用例（4 terminal 真 / 4 active 假）。
- **边界**：S2+S1 共同提交项。`runtime/index.ts` 属 domain 包内 barrel（S2 可改），但新增导出需在交接卡标 `@S1`，由 S1 同步 arch guard / 协调 S5 消费侧。改动小、无签名破坏。
---

## ✅ M2 收口摘要（已并入 main `4a6e628f`）

- **SSOT isTerminalRunStatus（主项）**：`par/domain-ssot` → 合入 main `006125b9`（`LEGAL_TRANSITIONS` 无出边推导 + barrel + 10 一致性测试，契约冻结）。
- **纯测试补覆盖 5 批**：`par/domain-cov2`（grant/buildScopedGrantScopeFromPending 分支）、`cov3`（wechat-tools allowlist 边缘，分支 100%）、`kcov`（project-knowledge + task-procedure + toFixSuggestion + knowledge/network 纯辅助）、`refine`（grant-path 纯辅助 + network-allowlist + store-contract）、`status`（SSOT status partition active-main vs terminal）。
- **5-gate**：domain tsc ✓、lint 0 警、全测试 PASS。
