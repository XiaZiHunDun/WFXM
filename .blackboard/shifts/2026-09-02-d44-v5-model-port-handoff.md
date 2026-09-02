# D44 — P5 Model Port 物化（2026-09-02）

**批次**：D44（P5 Model Port）· 主线：ports/adapters/api · 语言：TS

**目标**：把 Model Port 从"隐性承载"物化为同一真相源，供 adapter 构建与 llm-pricing 记账统一消费；6→7 物化 Core Port。

## 交付（5 commit，已备推 origin/main）

| commit | 内容 |
| --- | --- |
| `7dfb8de6` | docs(spec) P5 Model Port design |
| `438ae193` | feat(ports) `model-port.ts` `resolveModelForRole(env,role)` 纯函数 + barrel + index 注释 |
| `cd9b34e2` | refactor(adapters) `model-router.ts` 经 Model Port 构建 LLMAdapter + `resolveLLMModel` 重导出 + 测试 |
| `3b0fccea` | refactor(api) `llm-pricing.ts` 记账统一走 `resolveModelForRole(env,"plan")` |
| `56a2b873` | chore(arch) arch guard `section7-1-model-port.test.ts` + C12 扩展 + DESIGN §7.1/§7/line700 + port-catalog + sign-off |

## 关键决策

- 纯函数"实现即接口"，无 composition root 注入（model 选择由 env 驱动，非可注入时钟；ClockPort 先例不套用）
- 计划角色记账统一；exec 记账不在范围（D45 候选）
- `pickLLMProvider` / `execModelTrace` 公共面保留；§14 三 caller 不动；`wechat-inbound-butler.ts` 不动

## 5-gate

typecheck 全包 PASS / lint 0 警 / arch guard 216 PASS / 主测试 1479 PASS / test:archived 101 PASS。唯一 fail=`db-open.test.ts` postgres 实连（AI 沙箱无真实 PG，环境基线，与 D44 无关）。file-size 门禁 `owner-routes.ts` 1262>1200 属既有状态、非本班引入、不在范围。

## 验证留给 operator

5-gate 中 postgres 实连项需在 operator 终端（`CI= pnpm test`）复核 closes db-open。Model Port 纯函数逻辑已由单测覆盖，无 live smoke 依赖。

## 下一步

push origin/main；后续 batch 候选（D45 起）：exec 记账（owner 真撞）、Repository Port（等第二持久化实现）、Channel Port（等 Slack/Telegram 真接生产）。
