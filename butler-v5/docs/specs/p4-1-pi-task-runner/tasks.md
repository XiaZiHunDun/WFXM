# P4.1 实施任务

## 任务 1 — Ports 会话契约

- [x] 新建 `packages/ports/src/core/pi-task-session.ts`，实现 `PiTaskSessionStatus / PiTaskPendingStep / PiTaskSessionSnapshot / PiTaskSessionRecord / PiTaskSessionStore`。
- [x] `packages/ports/src/index.ts` 增加 `export * from "./core/pi-task-session.js"`。
- [x] `pnpm --filter @butler/ports typecheck`。

## 任务 2 — 模型层

- [x] 新建 `packages/runtime/src/execution/pi-model.ts`。
- [x] `resolvePiModelFromEnv` 读取 `MINIMAX_BASE_URL / MINIMAX_CN_API_KEY / MINIMAX_API_KEY / MINIMAX_MODEL / BUTLER_V5_PI_MAX_TOKENS`，缺关键值抛明确错误。
- [x] `createPiStreamFn` 用 `completeSimple + retryAssistantCall`，温度 0，429/5xx 重试 3 次，返回 `AssistantMessage` 事件流。
- [x] 增加最小单测：无 env 抛错、成功回复转事件流、错误回复转 `error` 事件。

## 任务 3 — 原生工具

- [x] 新建 `packages/runtime/src/execution/pi-native-tools.ts`。
- [x] 实现 `resolveInsideWorkspace`：绝对路径越界、`..`、symlink 逃逸拒绝。
- [x] 实现 `read / write / edit / bash / grep / find / ls` 七个 `AgentTool`。
- [x] 输出上限：read 64KiB/2000 行，write 64KiB，bash 32KiB，grep/find 200 条。
- [x] `bash` 只继承安全环境变量，非零退出码返回 `isError` 且带 exit code。
- [x] 新建 `pi-native-tools.test.ts`，覆盖七个工具成功路径 + 路径逃逸 + 非零退出码 + edit 未匹配。

## 任务 4 — 工具名归一化

- [x] 新建 `packages/runtime/src/execution/pi-tool-name-map.ts`，实现映射表与 `normalizePiToolName`。
- [x] 新建 `pi-tool-name-map.test.ts`，覆盖 7 个映射与未知工具原样返回。

## 任务 5 — 任务运行器与单飞锁

- [x] 新建 `packages/runtime/src/execution/pi-task-runner.ts`。
- [x] 实现 `MemoryPiTaskSessionStore`。
- [x] 实现 `GlobalAgentLock`（FIFO、activeTaskId、queueLength）与模块级 `globalAgentLock`。
- [x] 实现 `PiTaskRunner.open/load/start/resume/pause/close/list`。
- [x] `beforeToolCall`：预算检查 → 审批检查 → 记录 pendingStep → `{block:true,terminate:true}`。
- [x] `resume`：执行/拒绝 pending step，替换同 toolCallId 的 blocked toolResult，再继续 Agent。
- [x] 快照：每轮结束 `JSON.parse(JSON.stringify(messages))` 存 store；恢复时重建 Agent。
- [x] 同一任务重复 start 抛 `PiTaskBusyError`。
- [x] `createDefaultApprovalPolicy`：`write/edit/bash` 默认审批，支持 `BUTLER_V5_PI_APPROVAL=never|always`。
- [x] 新建 `pi-task-runner.test.ts`，覆盖：read 任务、write 自动放行、bash 任务、审批暂停→批准、审批暂停→拒绝、单飞排队、跨 runner 快照恢复、预算耗尽。
- [x] `packages/runtime/src/execution/index.ts` 增加三个新模块导出。
- [x] `packages/runtime/package.json` 增加 `./execution/pi-model.js`、`./execution/pi-native-tools.js`、`./execution/pi-task-runner.js`、`./execution/pi-tool-name-map.js` exports。
- [x] `pnpm --filter @butler/runtime test` 全绿。

## 任务 6 — 管家层持久化

- [x] `packages/persistence/src/schema.ts` 增加 `taskSessions` 表定义。
- [x] 新建 `packages/persistence/src/migrations/0015_task_sessions.sql`。
- [x] `run-migrations.ts` 追加 `0015_task_sessions.sql`。
- [x] 新建 `packages/persistence/src/task-session-store.ts`，实现 `DrizzlePiTaskSessionStore`（load/save/delete/listByStatus）。
- [x] `packages/persistence/src/index.ts` 增加导出。
- [x] `packages/persistence/package.json` 增加 `./task-session-store.js` export。
- [x] 新建 `task-session-store.test.ts`：save→load 往返、pendingStep 保留、delete、listByStatus、重复迁移可执行。
- [x] `pnpm --filter @butler/persistence test` 全绿。

## 任务 7 — 无模型冒烟

- [x] 新建 `packages/runtime/scripts/p4.1-smoke.mts`。
- [x] 用假 `StreamFn` 覆盖 8 个场景：read、write、edit、bash、审批批准、审批拒绝、单飞排队、快照跨 runner 恢复。
- [x] 每项输出 `PASS/FAIL`，失败退出码非 0。
- [x] `pnpm exec tsx packages/runtime/scripts/p4.1-smoke.mts` 通过。

## 任务 8 — 评测驱动归一化

- [x] 新建 `scripts/eval/task-input.ts`，迁出 `run-task.ts` 的类型接口。
- [x] 修改 `scripts/eval/run-task.ts` 从新文件导入类型。
- [x] `run-task.ts` 在解析 task 后判断 `WFXM_EVAL_DRIVER=pi`，动态导入并调用 `runPiEvalTask` 后返回。
- [x] 新建 `scripts/eval/run-pi-task.ts`：工作区准备、真实模型 runner、逐 turn 审批恢复、归一化工具事件、测试前后运行、结果 JSON。
- [x] 确认 `task.realModel !== true` 时明确报错。
- [x] 用 agent-eval 的 5 条真实任务跑通 pi 驱动（见任务 9）。

## 任务 9 — 评测验证

- [x] 5 条冒烟（真实模型）：
  - `cap-code-edit-slugify`
  - `cap-code-edit-clamp`
  - `cap-approval-write-port`
  - `cap-approval-block-rm`
  - `cap-approval-append-readme`
- [x] 记录每条的工具轨迹、审批时序、测试结果、工作区断言。
- [x] 全量 40 条 `--repeats 1`，记录得分与失败分类（首轮 31/40，平均 77.5%；修复审批批次与注入仓库地图后 34/40，平均 85.0%）。
- [ ] `--repeats 2` 正式结论：单轮仍低于基线 92.5%，先补齐剩余失败（预算/审批触发一致性）再执行。
- [x] 与原生 gate v4 92.5% 对比，输出真实差异；不修改断言。

## 任务 10 — 回归与收尾

- [x] `pnpm typecheck`。
- [x] `pnpm lint`。
- [x] `pnpm exec vitest run packages/runtime packages/persistence`（根目录配置，50/50 通过）。
- [x] 检查 `git status`，确认只包含本规格文件清单内的变更。
- [x] 汇总 P4.1 结果、已知限制、P4.2 接入建议。
