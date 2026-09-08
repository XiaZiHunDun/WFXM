# v5 微信消息模拟验收 harness（免人工 · 进 CI）

> **交接对象**：Claude Code（后续开发）。
> **主线**：`butler-v5` 是唯一活动产品主线；v4 已退役。
> 交接日期：2026-09-03。本 PRD 状态对齐：5 acceptance 文件（4 核心 +
> `product-regressions` 含 /undo · spam-guard · llm_call 三处 regression lock）
> + `scenarios/realistic.test.ts` 35 场景已全部交付并实跑通过（**49/49 绿**）；
> 剩余仅为最终验证收尾（见 §5.2）。

## 1. 目标与动机

本轮全面验收的缺口是：既有检查以**单元/集成测试**为主（fixture/mock 直接调各包接口），
**没有端到端地走完整条真实链路**：真实微信入站 HTTP → run loop → 工具调用 → 审批 →
恢复执行 → 落库。缺的正是"真实项目开发场景"这一环。

目标：做一个**微信消息模拟器**，用**脚本化 LLM fixture 注入生产 wiring**，驱动真实
`/v1/wechat/inbound` 路径，做**确定性、免人工、进 CI** 的验收。不调真模型、不开真微信、
不起活服务，全部在本进程内完成，多次运行结果一致。

## 2. 已交付文件

它们都基于生产已内置的 fixture 缝，**未改任何生产代码**。

### 2.1 harness + acceptance-app 基础

| 文件 | 作用 |
| --- | --- |
| `butler-v5/tests/acceptance/harness.ts` | 共享 harness：`makeAcceptanceApp`（装配生产 wiring + Hono 路由）、`sendWechatMessage`（POST /v1/wechat/inbound + 解析响应）、`toolCallEntry`/`decisionEntry`/`textEntry` 辅助 |
| `butler-v5/apps/api/src/acceptance-app.ts` | `buildHonoApp(wiring)`：从 Wiring 挂载生产入站路由。放 apps/api 是因 `hono`/`createRoutes` 只在 apps/api 内解析（root 不可见），tests/ 直接 import hono 会失败。仅薄封装，不绕行生产逻辑 |

### 2.2 acceptance 用例文件（5 文件 / 14 用例 — 已交付、实跑通过）

| 文件 | 用例数 | 覆盖场景 |
| --- | --- | --- |
| `butler-v5/tests/acceptance/commands-approval.test.ts` | 3 | 核心命令 + 审批流：① `/记住` 命令捷径 LLM-free 返回「已记住」② 脚本化 LLM 以文本 Respond 返回普通答复 ③ write_file 触发审批（policy Ask → waiting_approval）→ 微信「确认」恢复执行 → run 达终态 succeeded |
| `butler-v5/tests/acceptance/fault-tolerance.test.ts` | 3 | 容错 / 降级路径：① 入站校验失败（缺 apiVersion）返回 400 + `invalid body`（非 500 / 不丢消息）② 同 conversationId 在 waiting_approval 上再次入站降级为「未完成审批」回复（`ActiveMainRunConflict` 兜底）③ fixture 耗尽时 LLM 返回降级文本（`[fixture exhausted: plan#N]`，非 500 / 非 HTML 错误页） |
| `butler-v5/tests/acceptance/subagent-multiturn.test.ts` | 2 | 多轮对话 + 跨 turn 工具调用：① 同 conversationId 第二轮沿用第一轮 history（同一 convId 产生 ≥ 2 条 run）② 跨 turn 工具调用：turn1 `write_file` paused → turn2 「确认」恢复 → run 终态 succeeded |
| `butler-v5/tests/acceptance/audit-state.test.ts` | 3 | 审计 + 跨重启状态：① 入站 → `eventStore` 写入 `ConversationStarted` 行（事件流 schema 不变量 correlationId / actorKind / actorId 验证）② write_file 审批通过后 `scoped_grants` 表写入 grant 行（capability 审计可追溯）③ 跨「重启」：close harness → 同 PGlite data dir 重开 → pending approval 仍可恢复 |
| `butler-v5/tests/acceptance/product-regressions.test.ts` | 3 | 产品层回归锁（owner 真撞问题触发后 ship，对应 §18 trigger 设计）：① `/undo`：真实审批恢复后 `undoLastWrite` 还原文件内容（工作区预先 `before` → fixture 写 `after` → 审批 → `/undo` 还原为 `before`，reply 含「已还原」）② 垃圾消息护栏：`"请".repeat(80)` 单字符重复 80 次触发 `detectSpam` 短路 LLM，reply 命中 `消息过长\|重复\|具体需求` 且 toolCalls=0（不消耗 fixture）③ LLM 遥测：普通对话产生 `step/llm_call` 事件且 status=ok |

### 2.3 realistic 场景文件（35 场景 — 已交付、实跑通过）

| 文件 | 场景数 | 覆盖 |
| --- | --- | --- |
| `butler-v5/tests/acceptance/scenarios/realistic.test.ts` | 35 | 产品层行为分析（脚本化"好 bot" fixture，非真 LLM）：A1-A10 真实开发（读 README / 改路由 / 跑测试 / 改 timeout / 删 dead import / git log / PR 描述 / typecheck / 加 unit test 等）；B1-B10 开放性（v5 问题 / 下一步 / 接手导览 / 最近 3 天 / 架构 risk / 撞坑 / 设计哲学 / 未用功能 / owner 应关心什么 / 1 周 focus）；C1-C10 边界（`y` / `好的` / `👌` 当确认 / 长消息 spam / 模糊 优化 / 跨天 上次聊到哪 / 两个 task 一起 / 重复确认 / 撤销刚才 / 多语言混合）；D1-D5 组合（写 + 跑 test + 失败 + 修 + 再跑 / 看看 后续追问 / 先 read 现在改 / 被打断 resume / 写完 问安全吗）。验收期产物：`_analyze.md`（gitignored 录制品类，每轮覆盖）。 |

## 3. 已验证的关键假设（依赖签名核对 — 全数匹配）

以下签名均已人工核对，harness 用法正确：

- `makeWiring(config)`：`apps/api/src/wiring.ts:55`，接受 `bridge/workerId/runtimeStore/runEngine/db/backfillConversation/mcp/stores/channels`，stores 可缺省落 null。
- `RunEngine(store, coordinator?, clock=systemClock)`：`packages/runtime/src/run-engine.ts:91`，harness 用 `new RunEngine(runtimeStore, undefined, systemClock)` ✓。
- `bootstrapMcpTools(env = process.env, { runtimeStore })`：`apps/api/src/mcp-bootstrap.ts:331` ✓。
- `createRoutes(app, wiring)` → `POST /v1/wechat/inbound`（`apps/api/src/routes.ts:62`），响应体 `{ conversationId, turnId, reply, meta:{ iterations, toolCalls, finalDecision, traces } }`，与 harness 解析一致 ✓。
- `BUTLER_V5_INTAKE_ENABLED=0` 时路由走 `runButlerLoop`（真实回退路径，含完整微信工具集 write_file + 审批链路），而非 `routeWechatIntake`（后者工具集不全）✓。
- fixture 缝：`BUTLER_V5_LLM_FIXTURE_DIR` 设置后 `pickLLMForRole(env, role)`（`packages/adapters/src/model-router.ts:112`）返回 `makeFixtureLLMAdapter({ fixtureDir, role })`，读 `<dir>/<role>.json`；`ModelRole = "plan"|"exec"|"intake"`，harness 写 `plan.json/exec.json/intake.json` 对齐 ✓。
- `/记住` 等命令由 `tryWechatInboundCommand` 命令捷径拦截（`routes.ts:80`），LLM-free 返回「已记住」✓。

> **当前实跑结果（2026-09-07）**：`pnpm vitest run tests/acceptance --pool=forks`
> → **6 test files passed / 49 tests passed / ~10.1s**（tests 累计 ~15.9s）；
> `pnpm vitest run tests/acceptance/scenarios/realistic.test.ts --pool=forks`
> → **1 test file passed / 35 tests passed / ~5.7s**（tests 累计 ~3.6s）。
> 4 核心 acceptance 文件（11 用例）+ `product-regressions.test.ts`（3 用例）+ `scenarios/realistic.test.ts`（35 场景）= **49/49 绿**。

## 4. 关键机制 / 约定

- **wiring 装配镜像 production**：PGlite、完整 stores（runtime/durable-memory/document/project-knowledge/procedure/task）、RunEngine、MCP off。
- **env 关键项**：`BUTLER_V5_DB=pglite`、`VITEST=true`、`NODE_ENV=test`、`BUTLER_V5_LLM_FIXTURE_DIR`、`BUTLER_V5_WORKSPACE_ROOT`、`BUTLER_V5_MCP_ENABLED=0`、`BUTLER_V5_INTAKE_ENABLED=0`（统一走 runButlerLoop）。
- harness 额外暴露 `db`（drizzle 句柄）与 `workspaceRoot`，供用例断言 run 状态 / 审计 / 审批产物。
- 每次用例前 `setFixtures`：`resetFixtureLLMCounters()` + 覆写各 role json。`afterAll` 必须 `app.close()`（关 MCP + DB + 清 tmp）。
- 新用例 rule：**只新增 `tests/acceptance/` 用例，不改 harness 之外的生产代码**；若遇 harness 签名不匹配，先回看 §3 再考虑修 harness。
- **测试隔离约定**：同 convId 上 run 处于 `waiting_approval` 时，再次入站非「确认」语义会触发 `ActiveMainRunConflict` 降级 reply（见 `fault-tolerance.test.ts` 用例 ②）。每个 fault / audit 用例独立 `conversationId`（如 `c-fixture-exhausted-isolation` / `c-audit-event-store` / `c-audit-grants` / `c-audit-restart`）避免跨用例状态污染；realistic 用例统一 `c-realistic-${scenario.id}`。

## 5. 剩余项（按优先级）

4 核心 acceptance 文件（11 用例）+ `product-regressions.test.ts`（3 用例）+ 35 realistic 场景已全部交付且实跑通过（**49/49 绿**，见 §2 / §3）。剩余仅以下：

### 5.1 后续扩展（owner 实测触发型，非待办）

Baseline Regression lock 三件套（`/undo` + `spam-guard` + `llm_call`）已落在 `product-regressions.test.ts`（3 用例，见 §2.2），不再属于「待办」范围。后续按 §18 trigger 制度，仅在 owner 实测中撞到新型问题时**按需扩展**对应 fixture assertion，不预设新增用例：

1. **`/undo` 扩展**：若 owner 撞到 `/undo` 在多文件 / 部分失败 / 与审批联动等场景的边界行为，按需新增 fixture assertion 扩展覆盖。
2. **`spam-guard` 扩展**：若 owner 撞到新型 spam 模式（多轮刷屏 / emoji spam / 跨日重发 / 短句堆叠等），按需新增 C-edge 用例扩展覆盖（现有 `_fixtures.ts` C4 已锁单字符重复场景）。
3. **`llm_call` 扩展**：若 owner 撞到真实 `llm_call` 失败 / 超时 / usage 计费异常（D23 / D24 闭环后），按需补 fixture assertion 显式锁 `step/llm_call` 事件 + usage 字段（与 §14 observability 一致性挂钩）。

### 5.2 [P1] 最终验证收尾

- typecheck + lint + 单目录测试 + 全量回归无退化；
- 验证 `013d1095` 引入的 CI acceptance step 仍 green（acceptance 已被纳入 CI，注意测试自身较慢需看 CI 是否已放宽 timeout）；
- 更新 `.blackboard/state.md` 主线记录（如需），同步 MEMORY.md Post-D43 段 acceptance harness 闭环项。

## 6. Claude Code 接手步骤

```bash
cd butler-v5
# 1) 实跑当前已交付 acceptance 用例
pnpm vitest run tests/acceptance --pool=forks
# 2) 实跑 realistic 35 场景
pnpm vitest run tests/acceptance/scenarios/realistic.test.ts --pool=forks
# 3) 若 owner 手撞触发 §5.1 三件套，新增对应 fixture assertion（不改生产代码）
# 4) 最终验证
pnpm typecheck && pnpm lint
pnpm test   # 或项目惯例的全量测试入口
```

## 7. 风险与注意点

- **测试较慢**（开创 DB + wiring + 多轮），每用例 30s 上限（audit-state 跨重启用例 test timeout 60s）；全量 CI 会显著拉长，需权衡。
- harness 设 `BUTLER_V5_INTAKE_ENABLED=0` 是**有意为之**（走 runButlerLoop 全工具集）；不要改成走 intake，否则 write_file 不可见、审批流测不了。
- `acceptance-app.ts` 放 apps/api 而非 tests/：Hono 依赖解析边界；不要挪动。
- `_analyze.md` 由 `scenarios/realistic.test.ts` `afterAll` 自动覆盖生成（提交时勿混入）；`recordings-archive/v*-pre-*-fix/*.json` 是 per-version LLM baseline fixture，WFXM 根目录 `.gitignore` 已 gitignore，不提交。
- 既有未提交改动（如 `.blackboard/state.md`、`AGENTS.md` 文档链接、`.trae/` IDE 元数据等）属先前验收遗留，与本 harness 无关，提交时勿混入。

## 8. 历史参考

- `4972ed94` — wechat end-to-end simulated acceptance harness（4 文件 / 11 用例首次 ship）。
- `aadf23ce` — 35 realistic owner-task scenarios for product-layer analysis（realistic 35 场景首次 ship）。
- `d226f33f` — read-only run_command bypass approval for owner（P1）。
- `46ef4db3` — capability telemetry + /undo command + spam guard（P1+P2 closure）[MANUAL-OVERRIDE]。
- `7a79c2d3` — plan role accepts minimax + record-real-llm noFixture plumbing。
- `1252143c` — per-version baseline archive（recordings-archive/，防录音对比基线丢失）。
- PRD 原交接日期 2026-09-03，状态对齐日期 2026-09-07。