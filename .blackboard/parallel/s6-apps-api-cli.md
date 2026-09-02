# S6 — apps/api + cli 会话（面层/wiring/工具）

**职责**：负责面向用户与集成侧——`apps/api/**`（HTTP、owner-routes、wiring、Composition Root）与 `cli/**`。新入口归一化为 Run Trigger。

## 独占路径

- `apps/api/**`
- `cli/**`

## 边界（不可动）

- **只消费公共面**：`@butler/domain` / `@butler/ports`（`core/*` 端口）/ `@butler/persistence`（`createRuntimeStore` 等）/ `@butler/runtime`。**不 import 对方包内部路径**。
- 需新增/改公共导出 → 提 PR 给 owning 会话或 S1 落，不直接在对方包文件里手改。
- 不改 ports barrel / DESIGN.md / state.md / 全局 arch guard / 各包 `package.json` exports（S1 处理）。
- 受保护：`wechat-inbound-butler.ts`（勿动）。

## 依赖/上游

- 依赖 S2/S3/S4/S5 已稳定的公共面；是并行链的末端，大部分"接线"在此收敛，天然最后合。

## 常规先手

- **wiring / Composition Root** 注入 store/provider 时：生产用 `createRuntimeStore`，隔离/测试/引导可用 `createInMemoryRuntimeStore`（D46）。这一段容易与 S5 耦合——先把 S5 的接口面冻结，再在本会话接线。
- owner-routes 拆分已扁平化（D45）：新路由按域拆到 `apps/api/src/owner-routes/`，聚合入口保持瘦身。
- **exec 记账（D47）** 若非先登录等，落到 apps/api 侧是最小面，优先在此会话。

## 最小门禁（提交前）

```bash
cd butler-v5/apps/api && pnpm exec tsc --noEmit
cd butler-v5/cli && pnpm exec tsc --noEmit
cd butler-v5 && CI= pnpm exec vitest run apps/api cli tests/architecture -q
pnpm exec eslint apps cli --ext .ts --max-warnings 0
```

## 当前相关待办

- **exec 记账（D47，若落入面层）**——主战场。
- 与 S5 协同 MemoryService 物化接线端（等 S1 ledger 立项）。