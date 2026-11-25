# Phase 6 — 闭环飞轮体系检查与验证（Tasks）

> 对应 [spec.md](spec.md)。按顺序执行；每个任务完成即跑对应验证，不批量攒证据。
> 约定：不自动 commit / push；每完成一个 P0 任务向 owner 汇报一句。

---

## T0 审计收口（已完成，无需再执行）

- [x] 六环节代码证据核实（`/使用` `/收集` `/分析` `/反馈优化` `/测评` `/回流`）
- [x] 实测：工作区干净、网关 healthz ok、服务 active
- [x] 实测：`weekly-digest.test.ts` 2 failed（时间炸弹）
- [x] 产出 spec.md / tasks.md

**结论**：10/25，开放回路；8 个断裂点（B-01…B-08）。

---

## T1 修复测评自身红灯（P0-1 / B-07）

- [x] 两个失败用例改为 `auditWindowAroundNow()`，窗口随真实时钟对齐固定 `NOW`

**文件**：`apps/api/src/weekly-digest.test.ts`

改动：
1. 两个失败用例的审计查询改为与固定 `NOW` 对齐（给 `listRecentAuditEvents` 传入 `now`/等价的窗口基准；若 store 接口不支持，则用 `windowMs = Date.now() - NOW + DAY_MS` 并在注释写明原因）。
2. 不要改业务代码来迁就测试。

验证：
```bash
pnpm exec vitest run apps/api/src/weekly-digest.test.ts
```
预期：18/18 通过。

回滚：仅测试文件，`git checkout` 即可。

---

## T2 分析环节接持久化 trace（P0-2 / B-01）

- [x] `countFailedRuns` 优先 `traceStore.list({sinceMs,untilMs})`，失败回退内存
- [x] 新增 `isFailedRunTrace`（domain），同时识别 `step/run_failed` 与 `run/finish|failure + error`
- [x] `/v1/owner/usage` 改用同一谓词（此前同样漏计真实失败）
- [x] 新增单测：DB 有数据 + 内存为空仍计数 2

**文件**：
- `apps/api/src/weekly-digest.ts`（`collectWeeklyDigest`）
- `apps/api/src/weekly-digest.test.ts`（新增用例）
- 可能需要 `packages/persistence/src/trace-store.ts` 的 `list` 过滤（已支持 kind / 时间）

改动：
1. `TraceReader` 增加可选异步读取；`collectWeeklyDigest` 优先 `wiring.traceStore.list({ kind: "step", limit })`，失败或缺失时回退 `getSharedLocalTracer()`。
2. `failedRuns` 统计口径保持"`kind=step` 且 `name=run_failed` 且落在窗口内"。
3. 过滤必须用事件 `createdAt`，与现有实现一致。

验证：
```bash
pnpm exec vitest run apps/api/src/weekly-digest.test.ts
```
新增用例：写入 1 条 `run_failed` 到 traceStore → `resetSharedLocalTracer()` 清空内存 → 周报仍统计到 1。

回滚：单文件逻辑，保留内存回退分支即可降级。

---

## T3 修复质量门禁配置（P0-3 / B-04）

- [x] `wechat.cwd` → `"."`，命令改为 `pnpm typecheck` / `pnpm lint`
- [x] 新增配置守卫单测：每个项目 cwd 必须真实存在

**文件**：`config/quality-gate.json`、`apps/api/src/wechat-quality-gate.test.ts`

改动：
1. `wechat.cwd` 由 `"butler-v5"` 改为 `"."`。
2. `wechat.commands` 改为真实门禁（建议：`pnpm typecheck`、`pnpm lint`，单测可按需），移除指向单文件的占位。
3. 新增单测：配置里的每个 `cwd` 在 `BUTLER_V5_WORKSPACE_ROOT` 下必须存在（防再次陈旧）。

验证：
```bash
pnpm exec vitest run apps/api/src/wechat-quality-gate.test.ts
```
手工：在主线会话执行 `/验`，输出"全部通过"或真实失败原因（不是 ENOENT）。

---

## T4 修复 dev-verify 解析（P0-4 / B-05）

- [x] `resolveDevVerifyCwd`：配置 cwd 不存在时回退 workspace root
- [x] 新增 3 个单测：wechat → root、未知项目 → root、配置 cwd 缺失 → root
- [x] 修正两个 scheduleAsyncDevVerify 用例（原先依赖不存在的 `butler-v5/`，修复后会跑真实 `pnpm test`）

**文件**：`apps/api/src/dev-quality-gate.ts`、`apps/api/src/dev-quality-gate.test.ts`

改动：
1. `resolveDevVerifyCwd`：gate 配置里没有该项目或 `cwd` 缺失时，返回 workspace root，而不是拼出不存在的子目录。
2. 不把生产命令写死在代码；新增注释说明 `BUTLER_V5_DEV_VERIFY_CMD` 应配置真实门禁。

验证：
```bash
pnpm exec vitest run apps/api/src/dev-quality-gate.test.ts
```
新增用例：未知 projectId → 返回 root；已知 projectId → 返回配置子目录。

---

## T5 记忆链补生产者（P0-5 / B-03，**需 owner 批准决策**）

- [x] 采用方案 A：`/记住` 与「记住：X」写 `candidate`，并提示「回复「确认记忆」后生效」
- [x] 同步更新 `wechat-commands.test.ts`（4 处）与 acceptance `commands-approval.test.ts`
- [x] 覆盖完整链：记住 → `/记忆候选` → `/确认记忆` → `/记忆`

**文件**：`apps/api/src/wechat-memory-commands.ts`、`apps/api/src/wechat-commands.test.ts`

方案 A（默认建议）：
1. `/记住` / "记住：X" 改为 `status: "candidate"`，回复改为「已记录候选（xxx），回复「确认记忆」生效」。
2. `/确认记忆` 已支持逐条与批量确认，复用即可。

方案 B（保守）：
1. 保持 confirmed；
2. 新增对话路径：识别明确偏好/约束陈述 → 生成 candidate + audit。

验证：
```bash
pnpm exec vitest run apps/api/src/wechat-memory-commands.test.ts
```
预期：A 方案下 `/记住` 后状态为 candidate，`/确认记忆` 后可被召回。

---

## T6 闭环开关文档化（P0-6 / B-02）

- [x] `docs/ENV.md` 新增 §15.1「闭环所需开关」，覆盖收集/分析/反馈/测评/回流
- [x] 校正 `BUTLER_V5_TRACE` 默认值（文档写 0，代码实际 `true`）
- [x] `docs/PROGRESS.md` 新增 Phase 6 小节

**文件**：`docs/ENV.md`、`docs/PROGRESS.md`

改动：
1. `ENV.md` 新增"闭环所需开关"表：周报、提醒、auto-promote、candidate-expires、agent-rag memory，注明默认值与开启后效果。
2. `PROGRESS.md` 新增 Phase 6 小节（审计结论 + P0 完成情况）。

验证：文档链接可用；不触代码。

---

## T7 回流入口：trace → 场景草稿（P0-7 / B-08）

- [x] 新增 `scripts/acceptance/trace-to-scenario.ts` + `pnpm trace:to-scenario`
- [x] 输出 `<turn>.json` 与 `<turn>.draft.test.ts`（`describe.skip`，不进 CI 红灯）
- [x] 单测覆盖参数解析 / 两种终态事件形状 / 骨架渲染 / slug
- [x] 实测：`--help` 正常；未知 turnId 中文报错并 exit 1

**文件**：新增 `scripts/acceptance/trace-to-scenario.ts`；`package.json` 加 `trace:to-scenario`

改动：
1. 复用 `trace:export` 的 DB 打开与过滤代码，按 `--turn <id>` 取该 turn 全部事件。
2. 输出 `tests/acceptance/scenarios/drafts/<turnId>.json` + 一个 `*.draft.test.ts` 骨架，**不写入正式场景目录、不修改现有断言**。
3. 缺 turnId / 无数据时给出中文用法提示。

验证：
```bash
pnpm exec tsx scripts/acceptance/trace-to-scenario.ts --help
```
用真实 turnId 生成草稿并由人工检查结构。

---

## T8 收口验证（全量）

- [x] `pnpm format:check` 全绿（顺带修复 HEAD 上已存在的 `tests/e2e-real/real-llm-dev-loop.test.ts` 格式问题）
- [x] `pnpm typecheck` 全绿
- [x] `pnpm lint` 全绿，0 warning
- [x] `pnpm test`：296 文件 / 2,552 通过 / 4 skipped / 0 failed
- [x] 定向 61 用例通过；`trace:to-scenario` CLI 实测通过
- [x] 生产 env 未改动（P0-6 只落文档）

```bash
pnpm format:check
pnpm typecheck
pnpm lint
pnpm test
```

要求：4 条全绿；记录通过数量到 `PROGRESS.md`。

手工：
- `/周报` 与 `/日志`、`/v1/owner/traces` 失败数一致；
- `/验` 在 WFXM 主线可运行；
- 生产 env 未擅自改动（除 owner 批准项）。

---

## 任务状态表

| ID | 任务 | 优先级 | 状态 |
|----|------|--------|------|
| T0 | 审计收口 | — | ✅ |
| T1 | 修复测评红灯 | P0 | ✅ |
| T2 | 周报读持久化 trace | P0 | ✅ |
| T3 | 门禁配置修复 | P0 | ✅ |
| T4 | dev-verify 解析修复 | P0 | ✅ |
| T5 | 记忆链补生产者 | P0 | ✅（方案 A） |
| T6 | 闭环开关文档 | P0 | ✅ |
| T7 | trace→场景草稿 | P0 | ✅ |
| T8 | 全量收口验证 | P0 | ✅ |
| P1-1…5 | 告警/聚类/基线保鲜/纠错/复盘队列 | P1 | 另起阶段 |
