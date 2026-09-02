# S2 — domain 会话（契约/类型/状态机 上游）

**职责**：负责 `packages/domain/**`——纯类型、契约（如 `RuntimeStore` 接口）、状态转换（`transitions`/`run-trigger`）、治理类型（`governance`）。全仓最上游，最少冲突，最易并行。

## 独占路径

- `packages/domain/**`

## 边界（不可动）

- 任何 `@butler/ports|persistence|runtime|adapters|apps` 之外的包都不得 import 进 domain（防环；domain 只能 import 标准库/Typescript 自身与同包内部）。
- 不改 ports barrel / DESIGN.md / port-catalog.md（归 S1）。
- 若需新增 domain 契约子路径供他包消费：D1 改 `packages/domain/package.json` 的 `exports`——**该文件属 S1 终审**，提 PR 由 S1 落。

## 依赖/上游

- 无下游消费方约束；改契约签名会波及 S3/S4/S5/S6，**签名变更前先发 `@` note 给对应会话**，或在 PR 描述里 @S1 让其在合并时统一协调。

## 常规先手

- 契约稳定优先：新增接口/类型导出走 `store-contract.ts` 或领域子包，产出被 S3/S4/S5 引用。
- 复读 `butler-v5/DESIGN.md`（概念/数据/扩展边界）再改。

## 最小门禁（提交前）

```bash
cd butler-v5/packages/domain && pnpm exec tsc --noEmit
cd butler-v5 && CI= pnpm exec vitest run packages/domain -q
pnpm exec eslint packages/domain --ext .ts --max-warnings 0
```

## 当前相关待办

- 多为被动：S3/S4/S5 暴露端口/持久化需求时，为其收敛/新增 domain 契约。无独占待办候选（D47 特征不落 domain）。