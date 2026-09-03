# v5 微信消息模拟验收 harness（免人工 · 进 CI）

> **交接对象**：Claude Code（后续开发）。
> **主线**：`butler-v5` 是唯一活动产品主线；v4 已退役。
> 交接日期：2026-09-03。状态：**半成品；`commands-approval.test.ts` 3 用例已实跑通过（1431ms），其余待办见 §5**。

## 1. 目标与动机

本轮全面验收的缺口是：既有检查以**单元/集成测试**为主（fixture/mock 直接调各包接口），
**没有端到端地走完整条真实链路**：真实微信入站 HTTP → run loop → 工具调用 → 审批 →
恢复执行 → 落库。缺的正是"真实项目开发场景"这一环。

目标：做一个**微信消息模拟器**，用**脚本化 LLM fixture 注入生产 wiring**，驱动真实
`/v1/wechat/inbound` 路径，做**确定性、免人工、进 CI** 的验收。不调真模型、不开真微信、
不起活服务，全部在本进程内完成，多次运行结果一致。

## 2. 已交付文件（未提交）

它们都基于生产已内置的 fixture 缝，**未改任何生产代码**：

| 文件 | 作用 |
| --- | --- |
| `butler-v5/tests/acceptance/harness.ts` | 共享 harness：`makeAcceptanceApp`（装配生产 wiring + Hono 路由）、`sendWechatMessage`（POST /v1/wechat/inbound + 解析响应）、`toolCallEntry`/`decisionEntry`/`textEntry` 辅助 |
| `butler-v5/apps/api/src/acceptance-app.ts` | `buildHonoApp(wiring)`：从 Wiring 挂载生产入站路由。放 apps/api 是因 `hono`/`createRoutes` 只在 apps/api 内解析（root 不可见），tests/ 直接 import hono 会失败。仅薄封装，不绕行生产逻辑 |
| `butler-v5/tests/acceptance/commands-approval.test.ts` | 核心命令 + 审批流用例（详见 §5） |

## 3. 已验证的关键假设（依赖签名核对 — 全数匹配）

以下签名均已人工核对，harness 用法正确：

- `makeWiring(config)`：`apps/api/src/wiring.ts:55`，接受 `bridge/workerId/runtimeStore/runEngine/db/backfillConversation/mcp/stores/channels`，stores 可缺省落 null。
- `RunEngine(store, coordinator?, clock=systemClock)`：`packages/runtime/src/run-engine.ts:91`，harness 用 `new RunEngine(runtimeStore, undefined, systemClock)` ✓。
- `bootstrapMcpTools(env = process.env, { runtimeStore })`：`apps/api/src/mcp-bootstrap.ts:331` ✓。
- `createRoutes(app, wiring)` → `POST /v1/wechat/inbound`（`apps/api/src/routes.ts:62`），响应体 `{ conversationId, turnId, reply, meta:{ iterations, toolCalls, finalDecision, traces } }`，与 harness 解析一致 ✓。
- `BUTLER_V5_INTAKE_ENABLED=0` 时路由走 `runButlerLoop`（真实回退路径，含完整微信工具集 write_file + 审批链路），而非 `routeWechatIntake`（后者工具集不全）✓。
- fixture 缝：`BUTLER_V5_LLM_FIXTURE_DIR` 设置后 `pickLLMForRole(env, role)`（`packages/adapters/src/model-router.ts:112`）返回 `makeFixtureLLMAdapter({ fixtureDir, role })`，读 `<dir>/<role>.json`；`ModelRole = "plan"|"exec"|"intake"`，harness 写 `plan.json/exec.json/intake.json` 对齐 ✓。
- `/记住` 等命令由 `tryWechatInboundCommand` 命令捷径拦截（`routes.ts:80`），LLM-free 返回「已记住」✓。

> ⚠️ **`commands-approval.test.ts` 已实跑通过（2026-09-03，3 tests passed，1431ms）**；fault-tolerance / subagent-multiturn / audit-state 用例尚待编写，见 §5。

## 4. 关键机制 / 约定

- **wiring 装配镜像 production**：PGlite、完整 stores（runtime/durable-memory/document/project-knowledge/procedure/task）、RunEngine、MCP off。
- **env 关键项**：`BUTLER_V5_DB=pglite`、`VITEST=true`、`NODE_ENV=test`、`BUTLER_V5_LLM_FIXTURE_DIR`、`BUTLER_V5_WORKSPACE_ROOT`、`BUTLER_V5_MCP_ENABLED=0`、`BUTLER_V5_INTAKE_ENABLED=0`（统一走 runButlerLoop）。
- harness 额外暴露 `db`（drizzle 句柄）与 `workspaceRoot`，供用例断言 run 状态 / 审计 / 审批产物。
- 每次用例前 `setFixtures`：`resetFixtureLLMCounters()` + 覆写各 role json。`afterAll` 必须 `app.close()`（关 MCP + DB + 清 tmp）。
- 新用例 rule：**只新增 `tests/acceptance/` 用例，不改 harness 之外的生产代码**；若遇 harness 签名不匹配，先回看 §3 再考虑修 harness。

## 5. 待办（按优先级）

1. **[必须] 跑通 `commands-approval.test.ts`**：`/记住` 捷径、LLM 文本 Respond、write_file 审批往返（policy Ask → waiting_approval → 微信「确认」→ 恢复执行 → run 达终态）。
2. **`tests/acceptance/fault-tolerance.test.ts`**（容错/降级路径）：入站异常→降级回复不丢消息、冲突 run 的 `ActiveMainRunConflict` 处理、fixture 耗尽降级。
3. **`tests/acceptance/subagent-multiturn.test.ts`**（子代理委派 + 多轮）：多轮对话挂起同一 conversationId、子代理结果回传终态。
4. **`tests/acceptance/audit-state.test.ts`**（审计 + 状态）：事件流水写入、审批授予记录、跨"重启"恢复（重开 harness 重放同一 conversation）pending approval 可恢复。
5. **验收收尾**：typecheck + lint + 单目录测试 + 全量回归无退化；决定是否纳入 CI（`.github/workflows/ci.yml`，注意测试自身较慢需放宽 timeout）；更新 `.blackboard/state.md` 主线记录。

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