# v5 Monorepo 并行开发索引（按包边界）

> 决策（2026-09-02 立项；2026-09-02 业主确认升级）：**按包边界长期并行** + **会话自治推进、固定里程碑批次汇聚** + 本目录承载交接文档。
> 语言：中文。合并策略 = main 主干，各会话开 `par/<area>` topic 分支并**自主推进、定期 rebase 自治适配**；S1 仅在**固定汇聚点**（里程碑/发布快照）统一 rebase + 解共享冲突 + 跑全量 5-gate 收口。

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
3. **会话自治推进、不逐项等合并**：在自己的 `par/*` 上推进**一批自洽 commits** 再 push，各自跑**本包最小门禁**自测。下游定期 `git rebase origin/main` 让上游改动自行流入并**自行适配**（适配责任在会话；共享文件冲突除外 → 标 `@S1` note 等汇聚）。
4. **固定汇聚点收口**：日常不逐项合 main。只有 S1 定的里程碑/发布快照才统一 rebase 各 `par/*` + 解共享冲突 + 全量 5-gate + 合回 main。
5. 依赖方向只允许：`domain ← ports/persistence/adapters ← runtime ← apps+cli`。反向跨层是架构违规，arch guard 会红。
6. `wechat-inbound-butler.ts`、`pyproject.toml`、`.claude/**` 等受保护项不得擅动（见根 AGENTS）。

## 标准会话开场仪式（每个新会话）

1. 读根 `AGENTS.md` + `butler-v5/DESIGN.md`（按必读表）。
2. 读 `.blackboard/state.md`（当前主线 + 下一步）与对应会话卡本文件。
3. `git fetch origin && git checkout -b par/<area> origin/main`（S1 除外，S1 在 main）。
4. 确认不碰共享文件后再开工。
5. **推进期定期 `git rebase origin/main`**（下游尤其）：让上游已入 main 的改动自行流入，就地适配，保持分支与 main 近同步。

## 门禁块（分两级）

**会话侧（push 前，本包最小门禁）**：
```bash
cd butler-v5/<自己包>
pnpm typecheck && pnpm exec eslint . --ext .ts --max-warnings 0   # 类型 + lint 0 警
pnpm exec vitest run <本包相关测试> -q                            # 本包回归
```
改跨层 import / arch guard：`bash scripts/butler-layer-import-gate.sh` / `CI= pnpm exec vitest run tests/architecture -q`。

**S1 侧（仅批次汇聚时，全量 5-gate）**：
```bash
cd butler-v5
bash scripts/typecheck-gate.sh        # typecheck + file-size + deadcode
pnpm exec eslint packages/ apps/ cli/ --ext .ts --max-warnings 0   # lint 0 警
CI= pnpm test                        # 全量回归（基线参考 nodes）
bash scripts/butler-layer-import-gate.sh   # 改跨层 import 时
```

## 合并协议（批次汇聚，S1 执行收口）

1. **会话侧（日常）**：在 `par/*` 上推进**一批自洽 commits** → 本包最小门禁 → push 跟踪分支。推进期定期 `git rebase origin/main` 自治适配上游；共享文件冲突不进自己分支，标 `@S1` note 等汇聚。
2. **汇聚触发（S1 定）**：到里程碑/发布快照时，S1 拉取各 `par/*` → 统一 rebase 到 main → 解共享/承重文件冲突 → 跑全量 5-gate。
3. **收口**：把关通过 → S1 合回 main，并同步 `DESIGN.md`/`port-catalog.md`/`state.md`/交接卡。
4. **非汇聚点不逐项合 main**；各会话保持与 main rebase 同步即可，无需等 S1 通知。

## Wave-1 已并入（2026-09-02，main `2f5068ba`）

- S2 domain（状态机全表补测，`1daa740f`）、S4 persistence（cross-impl 契约线束，`3981845c`）、S5 runtime（双重完成守卫/deadline 并发修复，`43f8a645`）。
- `par/domain` / `par/persistence` / `par/runtime` 已消费，勿在其上续开；新开请 rebase 到新 main。
- 详见 `.blackboard/shifts/2026-09-02-d47-parallel-wave1-handoff.md`。

## Wave-2 划分（2026-09-02 owner 重定向）

**Channel Port 退役**：owner 确认目前只用微信，S3 不接真 Channel。**Channel Port 从候选移除**，不作硬物化（DESIGN §7 禁造休眠接口）；微信接入维持现状。

新会话分配：
- **S6 apps/api+cli**：`par/exec-audit` — **exec 行为审计记账**（每次 exec/子进程执行 append `exec.executed` audit 事件）。锚点 `apps/api/src/workspace-tools.ts`、`mcp-spawn.ts`、`wechat/dev-quality-gate.ts`；audit 经 persistence `runtime-store.ts` 追加（注入 wiring）。
- **S2 domain / S4 persistence / S5 runtime**：各包**整理与完善**（owner 全部勾选：代码规范与技术债、文档与黑板整理、测试补强、依赖与门禁卫生），覆盖到包内。

## 当前待办候选（按所属会话存放）

见 `.blackboard/state.md`"下一步"。Wave-2：exec 行为审计记账（S6）、各包整理与完善（S2/S4/S5）。Channel Port 已退役；MemoryService（§12）静候第二实现/隔离需求触发。

## 批次汇聚点（固定里程碑/发布快照，S1 定义并推进）

- **触发**：S1 在 state.md 发布**下一个汇聚点**（如 `M1`、`R11` 发布快照），各会话在汇聚点前**自主推进多轮**；无需在每项完成时汇聚。
- **汇聚点内容**：S1 统一 rebase 各 `par/*` → 解共享冲突 → 全量 5-gate → 合 main → 更新交接卡。
- **当前计划**：首个汇聚点待 S1 在 `state.md` 宣布。此前各会话在其 `par/*` 上持续推进 + rebase 同步即可。