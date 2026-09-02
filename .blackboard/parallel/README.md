# v5 Monorepo 并行开发索引（按包边界）

> 决策（2026-09-02，业主确认）：**按包边界长期并行** + **每会话独立分支、由编排会话合 merge** + 本目录承载交接文档。
> 语言：中文。合并策略 = main 主干，各只读会话开 `par/<area>` topic 分支，S1 负责 rebase/merge 到 main 并跑全量 5-gate。

## 会话表（每人/每会话认领一行）

| 会话 | 角色 | 独占路径（可提交） | 典型工作 |
| --- | --- | --- | --- |
| **[S1 orchestration](./s1-orchestration.md)** | 编排/集成 | `.blackboard/**`、`DESIGN.md`、`packages/ports/port-catalog.md`、`packages/ports/src/index.ts`、全局 `tests/architecture/*.test.ts` | 收口共享文件、把关加载、合并各 `par/*` 分支、维护 state/handoff |
| **[S2 domain](./s2-domain.md)** | 契约层 | `packages/domain/**` | 纯类型/契约/状态机/trigger（上游、最少冲突） |
| **[S3 ports+adapters](./s3-ports-adapters.md)** | 端口/适配层 | `packages/ports/src/core/**`（除 `index.ts` 由 S1 收口）、`packages/adapters/**` | Repository/Model/Channel Port 与 provider 实现 |
| **[S4 persistence](./s4-persistence.md)** | 持久化 | `packages/persistence/**`（除 `memory/` 若复用） | store、migration、backfill、事件桥 |
| **[S5 runtime](./s5-runtime.md)** | 运行引擎 | `packages/runtime/**` | run engine、capability boundary、grant/approval 服务 |
| **[S6 apps/api+cli](./s6-apps-api-cli.md)** | 面层 | `apps/api/**`、`cli/**` | wiring、owner-routes、exec 记账、工具面 |

## 硬规则（全会话一致，违反即不可并入）

1. **只改自己独占路径**。需要跨会话暴露/消费新符号时：不改对方包，先写 `@` 依赖 note 给 owning 会话或 S1 排队。
2. **共享/承重文件一律归 S1**：`.blackboard/**`、`DESIGN.md`、`packages/ports/port-catalog.md`、`packages/ports/src/index.ts`（barrel）、`package.json`（各包 exports/依赖别名）、全局 `tests/architecture/*.test.ts`、`AGENTS.md`/`CONTRIBUTING.md`。任何会话不得直接改（含 `[MANUAL-OVERRIDE]` 也须 S1）。
3. **提交前跑前置门禁**（各卡有最小集）；合并前 S1 跑全量 5-gate。见 [门禁块]
4. 依赖方向只允许：`domain ← ports/persistence/adapters ← runtime ← apps+cli`。反向跨层是架构违规，arch guard 会红。
5. `wechat-inbound-butler.ts`、`pyproject.toml`、`.claude/**` 等受保护项不得擅动（见根 AGENTS）。

## 标准会话开场仪式（每个新会话）

1. 读根 `AGENTS.md` + `butler-v5/DESIGN.md`（按必读表）。
2. 读 `.blackboard/state.md`（当前主线 + 下一步）与对应会话卡本文件。
3. `git fetch origin && git checkout -b par/<area> origin/main`（S1 除外，S1 在 main）。
4. 确认不碰共享文件后再开工。

## 门禁块（提交/合并且 S1 把关前必跑）

```bash
cd butler-v5
bash scripts/typecheck-gate.sh        # typecheck + file-size + deadcode
pnpm exec eslint packages/ apps/ cli/ --ext .ts --max-warnings 0   # lint 0 警
CI= pnpm test                        # 全量回归（基线参考 nodes）
bash scripts/butler-layer-import-gate.sh   # 改跨层 import 时
```

对改 arch guard / 文档：`CI= pnpm exec vitest run tests/architecture -q`。

## 合并协议（S1 执行，其余会话只发 PR/MR）

1. 会话在 `main` 拉到最新、在自身 `par/*` 完成并自测（本卡最小门禁）。
2. 向 S1 提交 PR（或会话内标注 ready），S1 rebase `par/*` 到 main + 跑全量 5-gate。
3. S1 把关通过 → S1 合回 main，并同步 `DESIGN.md`/`port-catalog.md`/`state.md`/交接卡。
4. 冲突集中发生在共享文件 → S1 作为唯一解开者。

## 当前待办候选（按所属会话存放）

见 `.blackboard/state.md`"下一步"。D47 候选：exec 记账（S6 apps/api）、Channel Port（S3）、MemoryService 物化（横跨 S3/S5/S6，需 S1 领衔清单）。

## Wave-1 已并入（2026-09-02，main `2f5068ba`）

- S2 domain（状态机全表补测，`1daa740f`）、S4 persistence（cross-impl 契约线束，`3981845c`）、S5 runtime（双重完成守卫/deadline 并发修复，`43f8a645`）。
- `par/domain` / `par/persistence` / `par/runtime` 已消费，勿在其上续开；新开请 rebase 到新 main。
- 详见 `.blackboard/shifts/2026-09-02-d47-parallel-wave1-handoff.md`。