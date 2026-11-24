# Phase 4 P0+P1 任务清单（2026-11-24）

对应 spec：`docs/plans/active/phase4-real-project-2026-11-23/spec.md` §10。

## P0 — acceptance harness 走真实 intake

- [x] T1 `tests/acceptance/harness.ts`
  - 选项新增 `intake?: boolean`（默认 `false`）。
  - 按 `intake` 设置 `process.env.BUTLER_V5_INTAKE_ENABLED`（`"1"`/`"0"`）与局部 `env`；
    保存旧值，`close()` 复原。
  - `opts.overrides` 逐键写入 `process.env`（保存旧值），`close()` 复原。
  - 验证：现有 acceptance 用例行为不变（默认 intake 关）。

- [x] T2 新增 `tests/acceptance/dev-delegate-approval.test.ts`
  - 用例 1（默认开关）：`intake: true` + `BUTLER_V5_SUBAGENT_ENABLED=1`；
    plan fixture 发 `delegate_to_subagent(role="exec")`，exec fixture 发 `write_file`；
    断言 `devSessionRunId("u-owner")` 的 write_file grant 存在，且 `child-note.txt`
    最终写入 `app.workspaceRoot`。
  - 用例 2（开关关闭）：追加 `BUTLER_V5_DEV_SESSION_AUTO_GRANT=0`、
    `BUTLER_V5_DELEGATION_PREGRANT=0`；断言无 dev-session grant、出现
    `child-<父会话>-` 待审批步骤、文件未写入；父会话发「确认」后文件写入。
  - 两个用例均启动 `runSubagentWorker`（`intervalMs: 20`，静默 logger），
    `finally` 中 stop + close；使用 `waitFor` 轮询而非固定 sleep。

## P1 — Demo 控制台对齐真机

- [x] T3 `scripts/demo-server.ts`
  - 真实模式默认 `intake: true`，`BUTLER_V5_DEMO_INTAKE=0` 可关回；
    脚本化模式保持 `intake: false`。
  - 真实模式默认 `BUTLER_V5_SUBAGENT_ENABLED=1`（未显式设置时），并启动
    `runSubagentWorker`（`intervalMs: 2000`）。
  - `rebuild()` 与退出流程先 stop worker 再 close app；重建后重新启动。
  - 控制台聊天框「确认」复用既有 `/demo/api/chat` → intake → inline approval。

- [x] T4 `tests/e2e-demo/console.spec.ts`
  - 新增「文字回复确认完成审批」：触发 write_file 待审批 → 聊天框发「确认」→
    断言待审批清空、状态「就绪」、bot 气泡含 `wrote demo-note.txt`。

- [x] T5 `docs/deployment/DEMO.md`
  - 记录脚本化 / 真实 LLM / 真机三种模式差异，以及
    `BUTLER_V5_DEMO_REAL_LLM=1`、`BUTLER_V5_DEMO_INTAKE=0` 用法。

## 验证

- [x] T6
  - `pnpm vitest run tests/acceptance/dev-delegate-approval.test.ts`
  - `pnpm vitest run tests/acceptance/subagent-multiturn.test.ts`
  - `pnpm vitest run apps/api/src/delegate-capabilities.test.ts apps/api/src/dev-session-grant.test.ts apps/api/src/wechat-inline-approval.test.ts`
  - `pnpm test:e2e:demo`
  - `pnpm typecheck` && `pnpm lint`

## 边界

- 不自动提交 / 推送。
- 真机微信 `hello3.txt` 待审批（`ee37d807-...`）需 owner 在微信回复「确认」。
