# P5 Model Port — 设计 spec (D44)

> **For agentic workers:** 配套实施计划见 impl 阶段逐 commit（T1 物化 Port → T2 adapters 重构 → T3 记账统一 → T4 arch guard + docs）。
> **背景**:P5 端口化完整性把 `Model Port` 列为"如出现多 Provider 协议/记账统一需求再物化"（`v5-post-boundary-roadmap-2026-08.md` P5 § + DESIGN §7 line 281）。已 ship 的 D24 costUsd 记账（`apps/api/src/llm-pricing.ts`）自己独立复刻了一份 provider 选择逻辑（`resolveCurrentLlmModel`，注释自述 "mirrors pickLLMProvider"），与真正跑执行的 `packages/adapters/src/model-router.ts` 存在真实 drift。D44 物化 Model Port，让"选哪个 provider+model"成为单一真相源，适配器构建与记账统一消费。
> **优先级**:P5 Model Port only — 纯角色级模型解析统一；不动 §14 三个 load-bearing caller、不建 DI 休眠接口、不迁适配器整体。
> **影响面**:`packages/ports/src/core/model-port.ts`（新）；`packages/adapters/src/model-router.ts` 重构；`apps/api/src/llm-pricing.ts` 记账统一；`packages/ports/src/index.ts` + 头部注释；arch guard（`section7-1-port-snapshot.test.ts` C12 扩 1 + 新 `section7-1-model-port.test.ts`）+ DESIGN §7/§7.1/line700 + `port-catalog.md`。
> **预估 ops**:~8 file ops / ~+180 prod+test / ~+30 doc-only / 5 commits (1 spec + 4 impl) / ~16 测试 cases

---

## 1. 目标

物化 P5 Model Port，统一"角色级 provider+model 选择"单一真相源：

1. **单一真相源** — `resolveModelForRole(env, role) → { provider, model }` 定义在 `packages/ports/src/core/model-port.ts`（纯函数，无 IO / 无适配器依赖）。
2. **适配器构建走 Port** — `model-router.ts` 从 Port 解析结果按 provider 构建 `LLMAdapter`（保留 fixture 覆盖 + 既有公开面 `pickPlanLLM / pickExecLLM / pickIntakeLLM / pickLLMForRole / execModelTrace`）。行为与现状**等价**。
3. **记账统一走 Port** — `llm-pricing.ts` 的 `resolveCurrentLlmModel` 改为映射 Port 的 `resolveModelForRole(env, "plan")?.model`；消除与 `model-router` 的 drift（补上 MiniMax 与 `BUTLER_V5_MODEL_*` 覆盖）。
4. **§14 三个 caller 不动** — `wechat-inbound-butler / subagent-worker / approval-resume` 与 `llm-pricing.js` 的 3 helper 导出保持（§14 arch guard 锁的消费链不破坏）。
5. **§7 原则遵守** — "实现即接口"：Model 选择是 env 驱动的纯逻辑，无第二个实现 / 无需 Composition Root，故设纯函数而非 DI 接口；不造成休眠接口（DESIGN §7 line 281/294）。

---

## 2. 决策汇总

| 维度 | 决策 |
|------|------|
| 动机 | **(c) 真实记账统一需求** — D24 costUsd 记账复刻了 model-router 的选择逻辑，已实际 drift；正是 P5 明确的"记账统一需求"触发点，非为架构完整造接口 |
| Port 形态 | **纯函数集（"实现即接口"）** — `resolveModelForRole`；不定义 DI 接口 + 不注入，避免休眠接口（对标 Capability "实现即接口"先例） |
| 命名 | `ModelRole = "plan" \| "exec" \| "intake"`；`LlmProviderId = "anthropic" \| "deepseek" \| "minimax" \| "dashscope"`；`ResolvedModel { provider, model }` |
| 角色选择语义 | **完全等价于今日 model-router** — plan: Anthropic→(BUTLER_V5_MODEL_PLAN·DEEPSEEK_KEY→DeepSeek)→DashScope；exec: deepseek-name+key→DeepSeek else MiniMax else 回退 plan；intake: DeepSeek else 回退 plan。Anthropic model 显式 `ANTHROPIC_MODEL ?? "claude-sonnet-4-20250514"`（与 adapter 内部默认 + pricing 默认一致） |
| fixture 覆盖 | 仍在 model-router `pickLLMForRole`（`BUTLER_V5_LLM_FIXTURE_DIR`），不迁入 Port |
| execModelTrace | 保留在 model-router，**逻辑不变**（trace-only observability 字符串，复用 env + isDeepSeekName 辅助） |
| 记账统一 | `resolveCurrentLlmModel(env)` 签名不变（`string \| null`），body 改为 `resolveModelForRole(env,"plan")?.model ?? null`；§14 3 helper 导出保留 |
| 公共面保持 | `pickPlanLLM/pickExecLLM/pickIntakeLLM/pickLLMForRole/execModelTrace` 全部保留；`pickLLMProvider`/`LLMAdapter`/`LLMMessage` 及 `llm-provider.ts` 不动 |
| arch guard | `section7-1-port-snapshot.test.ts` C12 扩 `model-port.ts`（"6→7 物化 Core Port"）；新 `section7-1-model-port.test.ts` 锁 adapters→Port 方向 + llm-pricing 消费 Port + Port 纯净 |
| First-class event | **0 新增**（纯选择逻辑，无运行事件） |

**Drift 证据（D44 触发理由）** — `resolveCurrentLlmModel` 只认 `ANTHROPIC/DEEPSEEK/DASHSCOPE_*`（无 MiniMax、无 `BUTLER_V5_MODEL_PLAN/EXEC/INTAKE`）；而 `model-router.pickExecLLM` 默认跑 MiniMax-M3。即"执行在 MiniMax，记账却解析成 plan 的 DeepSeek/空" → costUsd 对不上真实模型。

---

## 3. 现状与 gap

### 3.1 已 ship
- D24 `apps/api/src/llm-pricing.ts`：`parseLlmPricing` / `computeCostUsd` / `resolveCurrentLlmModel` + `ModelPricing`；§14 arch guard（`section14-costusd.test.ts` 5 cases）锁 3 caller 消费链 + `TraceEvent.costUsd`。
- `packages/adapters/src/model-router.ts`：`pickPlan/Exec/IntakeLLM` + `pickLLMForRole` + `execModelTrace`；10 cases（`model-router.test.ts`）。`llm-provider.ts` 定义 `LLMAdapter`（api-level 协议接口，属 adapters，不进 ports）。
- D31 §7.1 snapshot：`ports/core/` 现有 7 port（channel/clock/credential-provider/event-store/outbox/projection/snapshot）+ `r2-shim.ts`。

### 3.2 真缺（1 gap）
- **记账与执行的选择逻辑两处独立**：`model-router`（执行）+ `llm-pricing.resolveCurrentLlmModel`（记账）各写一份 provider 选择，已实际 drift（MiniMax + `BUTLER_V5_MODEL_*` 未进记账）。这是 DESIGN §6.2 明确归给 Model Port 的"用量记账"职责（line 245-247）。

### 3.3 文档 drift
- DESIGN §7.1 Model 行 = ⚪ 隐性承载（YAGNI，line 320）→ 物化为 ✅ `model-port.ts`。
- `port-catalog.md` §3 Model Port 仍列"待物化"→ 移除并升 §1。
- `packages/ports/src/index.ts` 头部注释 + DESIGN §7 audit"7 port"叙述 + DESIGN line 700 pricing 引用 → 同步为 Model Port。

---

## 4. 设计

### 4.1 Port：`packages/ports/src/core/model-port.ts`（新，纯函数）

```typescript
/** 角色级模型选择 — P5 Model Port（DESIGN §6.2 记账/协议统一；"实现即接口"纯函数，无 DI 接口）. */
export type ModelRole = "plan" | "exec" | "intake"
export type LlmProviderId = "anthropic" | "deepseek" | "minimax" | "dashscope"

export interface ResolvedModel {
  readonly provider: LlmProviderId
  readonly model: string
}

/** 按角色解析当前 provider + model（env 驱动；纯函数无副作用）。 */
export function resolveModelForRole(
  env: Readonly<NodeJS.ProcessEnv>,
  role: ModelRole = "plan",
): ResolvedModel | undefined
```

- plan: `ANTHROPIC_API_KEY`→anthropic(`ANTHROPIC_MODEL ?? "claude-sonnet-4-20250514"`)；否则 model=`BUTLER_V5_MODEL_PLAN\|DEEPSEEK_MODEL\|"deepseek-chat"` + `DEEPSEEK_API_KEY`→deepseek；否则 `DASHSCOPE_API_KEY`→dashscope(`"qwen-turbo"`)；否则 `undefined`。
- exec: model=`BUTLER_V5_MODEL_EXEC\|MINIMAX_MODEL\|BUTLER_SMOKE_MINIMAX_MODEL\|"MiniMax-M3"`；deepseek-name(`startsWith("deepseek")`) + `DEEPSEEK_API_KEY`→deepseek；否则 `MINIMAX_API_KEY\|MINIMAX_CN_API_KEY`→minimax；否则回退 plan。
- intake: model=`BUTLER_V5_MODEL_INTAKE\|BUTLER_V5_MODEL_PLAN\|DEEPSEEK_MODEL\|"deepseek-chat"`；`DEEPSEEK_API_KEY`→deepseek；否则回退 plan。

只 import TypeScript 内置类型 + `NodeJS.ProcessEnv`。0 class / 0 fetch / 0 db / 0 adapters import（满足 D31 §7 thin-barrel + interface-only + 依赖方向向内）。

### 4.2 adapters 重构：`packages/adapters/src/model-router.ts`

- 从 `@butler/ports/core/model-port.js` import `resolveModelForRole, isDeepSeekModelName, type ResolvedModel`。
- 新增内部 `buildAdapter(r: ResolvedModel, env): LLMAdapter | undefined`：
  - anthropic → `makeAnthropicAdapter({ apiKey, model })`
  - deepseek → `deepseekAdapter(env, model)`（含 `buildDeepSeekRequestExtras`）
  - minimax → `minimaxAdapter(env, model)`（cn/intl key + baseUrl 归一）
  - dashscope → `makeOpenAICompatibleAdapter({ apiKey, baseUrl:"https://dashscope.aliyuncs.com/compatible-mode/v1", model:"qwen-turbo" })`
- `pickPlanLLM/pickExecLLM/pickIntakeLLM` = `buildAdapter(resolveModelForRole(env, role), env)`。
- `pickLLMForRole`：fixture 判断不变；非 fixture 时 switch role → `resolveModelForRole` + `buildAdapter`。
- `execModelTrace`：逻辑等价保留（读取 env 判断 exec provider）；行为不变。
- 暴露**新**导出 `resolveLLMModel(env, role): { provider, model } | undefined`（透传 Port 结果，供 apps 记账/观测消费）。

### 4.3 记账统一：`apps/api/src/llm-pricing.ts`

- `resolveCurrentLlmModel(env)` body 改为 `resolveModelForRole(env, "plan")?.model ?? null`（签名 `string | null` 不变）。§14 3 helper（`parseLlmPricing/computeCostUsd/resolveCurrentLlmModel`）+ `ModelPricing` 导出**全部保留**。
- 可选：新增 `resolveCurrentModelForRole(env, role)` 透传 Port（供未来按 exec 记账）；本 batch 先不加，避免未用导出。

### 4.4 arch guard
- `tests/architecture/section7-1-port-snapshot.test.ts` C12：required 数组 `+ "model-port.ts"`，注释 "6→7"。
- 新 `tests/architecture/section7-1-model-port.test.ts`：
  1. `ports/core/model-port.ts` 存在且导出 `resolveModelForRole / ModelRole / ResolvedModel`，且 0 `LLMAdapter` import、0 fetch/db。
  2. `model-router.ts`（adapters）`import ... from "@butler/ports/core/model-port.js"`（适配器依赖方向向内 Port）。
  3. `llm-pricing.ts`（apps）`import ... from "@butler/ports/core/model-port.js"` 且仍 `export function resolveCurrentLlmModel`。

### 4.5 测试策略（~16 cases）
| Suite | Cases |
|-------|-------|
| `packages/ports/src/core/model-port.test.ts`（新 ~8） | plan 4（Anthropic 默认/override；DeepSeek 默认 model；DashScope；无 provider→undefined）+ exec 2（MiniMax；deepseek-name） + intake 1 + exec 回退 plan 1 |
| `packages/adapters/src/model-router.test.ts`（扩 ~4） | 保持既有 10 例行为；加：pickLLMForRole 三种 role 在各 provider 配置下仍命中正确 provider（baseUrl 断言）；resolveLLMModel 透传 |
| `apps/api/src/llm-pricing.test.ts`（扩 ~4） | resolveCurrentLlmModel 既有 5 例全绿 + 加：`BUTLER_V5_MODEL_PLAN` override、`MINIMAX` 不影响 plan resolution、与 model-router 同一 env 返回同一 model（记账一致当断言）→ **核心记账一致性** |

### 4.6 边界遵守（DESIGN §）
- §3 6 硬规则 / §20 invariant / §10 governance：0 触（纯选择；不经 Policy；`LLMAdapter` 仍在 adapters）
- §5 domain-pure：0 触（Port 在 ports 不在 domain；`LLMAdapter` 不进入 ports/domain）
- §6.2：Model Port 承接"协议适配 + 记账"统一选择面（不承载副作用；模型调用仍只经 `LLMAdapter.complete`）
- §7 thin-barrel / interface-only / 依赖方向向内：满足（model-port 纯函数；adapters→ports 向内）
- §7.1：Model 行 ⚪→✅；`ports/index.ts` 头部注释 "6→7 物化 Core Port"
- §14：3 caller + llm-pricing 3 helper + TraceEvent.costUsd 锁**不变**
- §18 / Schedule：0 触

---

## 5. 文件 ops 清单（预估 ~8 file ops）

| 文件 | ops | 说明 |
|------|-----|------|
| `packages/ports/src/core/model-port.ts` | 新增 ~55 | `resolveModelForRole` + 类型 |
| `packages/ports/src/core/model-port.test.ts` | 新增 ~90 | ~8 cases |
| `packages/ports/src/index.ts` | +1 / -1 comment | `export * from "./core/model-port.js"` + 头部注释 6→7 |
| `packages/adapters/src/model-router.ts` | ~-40/+45 | 改从 Port 构建 adapter + `resolveLLMModel` |
| `packages/adapters/src/model-router.test.ts` | ~+30 | 加 provider 命中 + resolveLLMModel |
| `apps/api/src/llm-pricing.ts` | ~-10/+8 | `resolveCurrentLlmModel` 走 Port |
| `apps/api/src/llm-pricing.test.ts` | ~+35 | 记账一致性 cases |
| `tests/architecture/section7-1-port-snapshot.test.ts` | +1 | C12 加 model-port.ts |
| `tests/architecture/section7-1-model-port.test.ts` | 新增 ~45 | 3 cases |
| `butler-v5/DESIGN.md` + `packages/ports/port-catalog.md` + `ports/src/index.ts` 注释 | doc-only ~+30/-8 | §7.1 ✅ / §7 audit / line700 / catalog §1+§3 |

---

## 6. 不做（明确范围外）

- **不迁 `LLMAdapter`/`llm-provider.ts` 进 ports** — 那是 api-protocol 具体协定面，属 adapters；Port 只承载中性 `{provider, model}` 选择（DESIGN §6.2 职责划分）
- **不建 DI 接口 + Composition Root 注入** — 无第二实现需求时，纯函数是"实现即接口"；造接口 = 休眠接口（违反 §7 line 294）
- **不动 §14 三个 caller** — load-bearing + arch-locked；消费链保持
- **不改 `wechat-inbound-butler.ts` 等** — 本次只动 `model-router` + `llm-pricing` + ports barrel
- **不加 exec 记账** — 先统一 plan 记账（主动能；exec 记账留未来 owner 真撞再挂）
- **不删 `pickLLMProvider` / `execModelTrace` 原语义** — 保留公共面，避免无关破坏
- **无新 migration / 新 first-class event** — 纯选择逻辑

---

## 7. 触发链 & 后续
1. 实施：4 tasks（T1 Port → T2 adapters 重构 → T3 记账统一 → T4 arch guard + docs）
2. 验证：每 commit 后 typecheck + lint + 对应 focused vitest；收尾 `CI= pnpm exec vitest run`（生产）+ test:archived + arch guard（AI 沙箱注 `CI=true`，需 `CI= pnpm test`）
3. 记忆：写 `memory/project-fix-D44-v5-model-port-2026-09-02.md`
4. commit：5 commits（1 spec + 4 impl）conventional
5. handoff：`.blackboard/shifts/2026-09-02-d44-v5-model-port-handoff.md`
6. 后续 batch 候选：D45（如触发）exec 记账、Repository Port（等第二持久化实现）、Channel Port（等 Slack/Telegram 真接生产）

---

## 8. 关联
- P5 Model Port 触发条件 — `docs/plans/active/v5-post-boundary-roadmap-2026-08.md` P5 §
- §6.2 Model Port 职责（协议适配/超时/fallback/用量记账）— `DESIGN.md` line 245-247
- D24 costUsd 记账 — `apps/api/src/llm-pricing.ts` + `tests/architecture/section14-costusd.test.ts`
- D31 §7 thin-barrel/interface-only/依赖方向向内 — `tests/architecture/section7-ports-main.test.ts`
- D37 §7.1 snapshot — `tests/architecture/section7-1-port-snapshot.test.ts`
- ClockPort 先例（构造注入 + 确定性测试） — `packages/ports/src/core/clock.ts`；本批对 Model 用纯函数、不引入构造注入（model 选择由 env 驱动，非可注入时钟）
- `LLMAdapter` 接口 — `packages/adapters/src/llm-provider.ts`

---

**Spec version**: v1 (brainstorming closed 2026-09-02)
**Spec status**: awaiting owner review