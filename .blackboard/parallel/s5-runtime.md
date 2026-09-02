# S5 — runtime 会话（运行引擎/能力边界）

**职责**：负责 `packages/runtime/**`——run engine（主循环编排）、capability boundary、grant/approval 决策、Run Trigger 归一、跟 side-effect 咽喉相关的落库协调。

## 独占路径

- `packages/runtime/**`

## 边界（不可动）

- 消费 `domain` +（视现状）`ports`，不反向 import `apps / cli`。
- 若 runtime 当前直接 import persistence 的 store——需持久化能力时优先走端口/经注入，不写死到某 adapter 实现。新增对其它包的公共依赖变更 → 提 PR 由 S1 落 `package.json`。
- 不改 ports barrel / DESIGN.md / state.md / arch guard 全局文件。
- 涉及 grant/审批/approval 逻辑的语义（Policy → wait_approval → ScopedGrant → Provider Boundary → Audit 链）守住 DESIGN §3 事实规则，改动前重读 `DESIGN.md`。

## 依赖/上游

- 依赖 S2（domain 契约）、S3（ports 端口，如 Repository Port）、S4（persistence store）。是 S6（apps/api）的主消费对象。

## 常规先手

- 主循环/重试/queue/compaction 改动跑 `packages/runtime` + 相应 harness 测试（`tests/` 相关）。
- 新增副作用必经副作用咽喉（Policy→…→Audit）；模型调用不走咽喉（D-series 事实规则）。

## 最小门禁（提交前）

```bash
cd butler-v5/packages/runtime && pnpm exec tsc --noEmit
cd butler-v5 && CI= pnpm exec vitest run packages/runtime -q
pnpm exec eslint packages/runtime --ext .ts --max-warnings 0
# 涉及 gateway/queue/workflow 时加：
CI= pnpm exec vitest run tests/gateway tests/test_p2_workflow_permissions.py-tests 2>/dev/null || true
```

> 注：部分历史 harness 编号来自 v4 脚本；以现有 `tests/` 实际文件为准。

## 当前相关待办

> ⚠️  **历史待办**：以下 Wave-3 任务已在 M2（main `4a6e628f`）全部收口完成，本段仅作归档留底。
>  ✅ 实际完成见末尾「M2 收口摘要」。

- **Wave-3 主项：SSOT `isTerminalRunStatus` 消费侧（S2+S1 协调，2026-09-02 立项）**
  - 现状：`packages/runtime/src/run-lifecycle.ts:176-187` 自维护本地 `TERMINAL_RUN_STATUSES` 常量 + `isTerminalRunStatus` 函数（与 domain `LEGAL_TRANSITIONS` 重复）。
  - 任务：**S2 已合入 main（`006125b9`）**。`git fetch && git rebase origin/main` 后：删除本地 `TERMINAL_RUN_STATUSES` 常量（178-183）与私有 `isTerminalRunStatus` 函数（185-187）；把 `isTerminalRunStatus` 追加到第 1-2 行的 `@butler/domain/runtime.js` import；`TERMINAL_RUN_STATUSES` 无需导入（仅本地函数曾用它）。保持 `transitionRunToTerminal`/`expireOverdueRuns` 行为不变。
  - **验证**：`packages/runtime` typecheck + 相关测试全绿；grep 确认 runtime 内不再有本地 `TERMINAL_RUN_STATUSES` 定义。
  - **依赖**：S2 已完成并经 S1 合入 main；现在可独立消费，完成后标 @S1 由 S1 收口。
  - 其余：exec 记账已落在 apps/api（D49），不落引擎层。
---

## ✅ M2 收口摘要（已并入 main `4a6e628f`）

- **SSOT 消费侧**：`par/runtime-ssot` → `22360a67`（删 `run-lifecycle.ts:176-187` 本地定义，改从 domain 导入；65/379 全过，行为零漂移）。
- **runtime-hardening**：`par/runtime-hardening` → double-completion no-op 修复（run-engine 读实际 status 而非猜 "succeeded"）+ cancelRunCascade 用 SSOT `isTerminalRunStatus`（跳过 expired 死端，修 `IllegalRunTransitionError` 级联中止）+ 7 模块分支覆盖测试。
- **5-gate**：runtime tsc ✓、lint 0 警、全测试 PASS。
