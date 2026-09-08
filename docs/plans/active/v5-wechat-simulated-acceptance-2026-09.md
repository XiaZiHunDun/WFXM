# v5 微信消息模拟验收 harness（免人工 · 进 CI）

> **交接对象**：Claude Code（后续开发）。
> **主线**：`butler-v5` 是唯一活动产品主线；v4 已退役。
> 交接日期：2026-09-03。本 PRD 状态对齐：`commands-approval` / `fault-tolerance` /
> `subagent-multiturn` / `audit-state` 四文件 + `scenarios/realistic.test.ts`
> 35 场景已全部交付并实跑通过；剩余仅为 /undo · spam-guard · llm_call
> 三处 regression lock 与最终验证收尾。

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

### 2.2 acceptance 用例文件（4 文件 / 11 用例 — 已交付、实跑通过）

| 文件 | 用例数 | 覆盖场景 |
| --- | --- | --- |
| `butler-v5/tests/acceptance/commands-approval.test.ts` | 3 | 核心命令 + 审批流：① `/记住` 命令捷径 LLM-free 返回「已记住」② 脚本化 LLM 以文本 Respond 返回普通答复 ③ write_file 触发审批（policy Ask → waiting_approval）→ 微信「确认」恢复执行 → run 达终态 succeeded |
| `butler-v5/tests/acceptance/fault-tolerance.test.ts` | 3 | 容错 / 降级路径：① 入站校验失败（缺 apiVersion）返回 400 + `invalid body`（非 500 / 不丢消息）② 同 conversationId 在 waiting_approval 上再次入站降级为「未完成审批」回复（`ActiveMainRunConflict` 兜底）③ fixture 耗尽时 LLM 返回降级文本（`[fixture exhausted: plan#N]`，非 500 / 非 HTML 错误页） |
| `butler-v5/tests/acceptance/subagent-multiturn.test.ts` | 2 | 多轮对话 + 跨 turn 工具调用：① 同 conversationId 第二轮沿用第一轮 history（同一 convId 产生 ≥ 2 条 run）② 跨 turn 工具调用：turn1 `write_file` paused → turn2 「确认」恢复 → run 终态 succeeded |
| `butler-v5/tests/acceptance/audit-state.test.ts` | 3 | 审计 + 跨重启状态：① 入站 → `eventStore` 写入 `ConversationStarted` 行（事件流 schema 不变量 correlationId / actorKind / actorId 验证）② write_file 审批通过后 `scoped_grants` 表写入 grant 行（capability 审计可追溯）③ 跨「重启」：close harness → 同 PGlite data dir 重开 → pending approval 仍可恢复 |

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
> → **5 test files passed / 46 tests passed / ~8.6s**；
> `pnpm vitest run tests/acceptance/scenarios/realistic.test.ts --pool=forks`
> → **1 test file passed / 35 tests passed / ~5.0s**。
> 4 acceptance 文件覆盖 11 用例 + realistic 覆盖 35 场景 = **46/46 绿**。

## 4. 关键机制 / 约定

- **wiring 装配镜像 production**：PGlite、完整 stores（runtime/durable-memory/document/project-knowledge/procedure/task）、RunEngine、MCP off。
- **env 关键项**：`BUTLER_V5_DB=pglite`、`VITEST=true`、`NODE_ENV=test`、`BUTLER_V5_LLM_FIXTURE_DIR`、`BUTLER_V5_WORKSPACE_ROOT`、`BUTLER_V5_MCP_ENABLED=0`、`BUTLER_V5_INTAKE_ENABLED=0`（统一走 runButlerLoop）。
- harness 额外暴露 `db`（drizzle 句柄）与 `workspaceRoot`，供用例断言 run 状态 / 审计 / 审批产物。
- 每次用例前 `setFixtures`：`resetFixtureLLMCounters()` + 覆写各 role json。`afterAll` 必须 `app.close()`（关 MCP + DB + 清 tmp）。
- 新用例 rule：**只新增 `tests/acceptance/` 用例，不改 harness 之外的生产代码**；若遇 harness 签名不匹配，先回看 §3 再考虑修 harness。
- **测试隔离约定**：同 convId 上 run 处于 `waiting_approval` 时，再次入站非「确认」语义会触发 `ActiveMainRunConflict` 降级 reply（见 `fault-tolerance.test.ts` 用例 ②）。每个 fault / audit 用例独立 `conversationId`（如 `c-fixture-exhausted-isolation` / `c-audit-event-store` / `c-audit-grants` / `c-audit-restart`）避免跨用例状态污染；realistic 用例统一 `c-realistic-${scenario.id}`。

## 5. 剩余项（按优先级）

四 acceptance 文件 + 35 realistic 场景已全部交付且实跑通过（46/46 绿，见 §2 / §3）。剩余仅以下：

### 5.1 [P1] Regression lock 三件套（与 §18 trigger 设计挂钩 — 等真实 owner 手撞再启用，未撞前不必新增用例）

1. **`/undo` regression lock**：`scenarios/realistic.test.ts` 中 C9「撤销刚才」已用 fixture 跑通正向 reply；待 `/undo` 命令（`d226f33f` 已 ship）在 owner 实测中撞到真问题，再补一条 fixture assertion 锁住 `commands-approval` 入口的撤销链路（与 `tryWechatInboundCommand` 拦截分支对齐）。
2. **`spam-guard` regression lock**：`scenarios/realistic.test.ts` 中 C4「长消息 spam」已跑通；待 owner 撞到真实长消息 / 多轮刷屏触发降级 reply 时，补一条 fixture assertion 锁住 spam-guard 命中条件（与 `46ef4db3` shipped 的 guard 对齐）。
3. **`llm_call` regression lock**：当前 `commands-approval` / `subagent-multiturn` 用例已隐含覆盖 `write_file` → `llm_call` 链路；待 owner 撞到真实 `llm_call` 失败 / 超时 / usage 计费异常（D23 / D24 闭环后），补一条 fixture assertion 显式锁 `step/llm_call` 事件 + usage 字段（与 §14 observability 一致性挂钩）。

### 5.2 [P1] 最终验证收尾

- typecheck + lint + 单目录测试 + 全量回归无退化；
- 决定是否纳入 CI（`.github/workflows/ci.yml`，注意测试自身较慢需放宽 timeout；acceptance 已被 `013d1095` 纳入 CI 的现实情况请以当时 CI 配置为准）；
- 更新 `.blackboard/state.md` 主线记录（如需），同步 MEMORY.md Post-D43 段 acceptance harness 闭环项。

## 6. Claude Code 接手步骤

```bash
cd /home/ailearn/projects/WFXM/butler-v5
# 1) 先跑通现有用例
pnpm vitest run tests/acceptance --pool=forks   # 或单文件跑通
# 2) 通过后补 fault-tolerance / subagent-multiturn / audit-state
# 3) typecheck + lint + 全量回归
pnpm typecheck && pnpm lint
pnpm test   # 或项目惯例的全量测试入口
```

## 7. 风险与注意点

- **测试较慢**（开创 DB + wiring + 多轮），每用例 30s 上限；全量 CI 会显著拉长，需权衡。
- harness 设 `BUTLER_V5_INTAKE_ENABLED=0` 是**有意为之**（走 runButlerLoop 全工具集）；不要改成走 intake，否则 write_file 不可见、审批流测不了。
- `acceptance-app.ts` 放 apps/api 而非 tests/：Hono 依赖解析边界；不要挪动。
- 交接前 uncommitted 的还有因之前验收留下的 `.blackboard/state.md`、`AGENTS.md` 文档链接修复、`.trae/` IDE 元数据等，属既有改动，与本 harness 无关，提交时勿混入。