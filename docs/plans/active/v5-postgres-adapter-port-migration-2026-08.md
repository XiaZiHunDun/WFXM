# Butler v5 — postgres adapter R2 Effect Tag → /core/* Port migration (2026-08)

> **状态**：Active planning（PRD 草案，待 operator review）
> **目的**：把仍在生产的 postgres 适配器对 R2 Effect Tag 的依赖收口到 DESIGN §7 物化的 `/core/*` 端口，再归档整文件
> **依赖**：R11.2 alignment shift（commit `4fed4e02`，B-soft 路径落地 port-catalog + package-membership 守卫）已就位
> **驱动**：DESIGN §7 "ports-stable × real-need driven" 准则 + invariant 16（monorepo 卫生）+ 长期可演进
> **路线图出处**：[`v5-post-boundary-roadmap-2026-08.md`](../decisions/v5-post-boundary-roadmap-2026-08.md) 的 "P5 端口化完整性" 已收口 ClockPort；本 PRD 把 P5 余项从"隐性承载"推到"物化"

## 1. 背景

R11.2 closure（commit `4fed4e02`）实证：`packages/ports/src/index.ts` 的 14 个 Effect Tag 中**5 个仍被生产代码消费**（`postgres-outbox/event-store/snapshot/projection.ts` + `config/src/index.ts`）；B-soft 路径把它们标 `@deprecated`，但**未**改 consumer。本 PRD 是下一段：把这 5 个 Tag 各自窄化为物化的 `/core/*` Port 接口，然后归档整文件。

## 2. Scope

### 2.1 In scope（本 PRD 覆盖）

| # | 工作 | 备注 |
| --- | --- | --- |
| 1 | 新增 `/core/outbox.ts`（`enqueue` / `claim` / `complete` / `fail` / `runWorker`） | 镜像 `postgres-outbox.ts` 公共 API |
| 2 | 新增 `/core/snapshot.ts`（`load` / `save`） | 镜像 `postgres-snapshot.ts` |
| 3 | 新增 `/core/projection.ts`（`apply` / `rebuild` / `register`） | 镜像 `postgres-projection.ts` |
| 4 | 调和 `EventStoreService`（R2 宽）vs `EventStorePort`（R10 窄） | 见 §5 CP-1 |
| 5 | 把 `packages/config/src/index.ts` 从 `Config` Tag 迁走 | 见 §5 CP-2 |
| 6 | 归档 9 个未消费 R2 Tag（见 §3.2） | 单 commit `git mv` 到 `_archive/packages/ports-effect-tag-scaffold/` |
| 7 | `packages/ports/port-catalog.md` 同步 | §2 R2 看板切换为"已迁/归档"；§1 加 outbox/snapshot/projection |
| 8 | `tests/architecture/package-membership.test.ts` 第 (4) 测试改写 | 不再"reminder R2 总线保留" |
| 9 | `DESIGN §7.1` 状态表新增 3 行 + R2 总线状态改"已归档" | |
| 10 | `state.md` 顶部段 + "## 上一班" 增加 R12 班段 | |

### 2.2 Out of scope

- postgres 适配器**内部**实现重写（如 Effect Layer → async/await 切换）—— orthogonal
- 引入第二持久化实现（RepositoryPort 物化的 trigger）—— YAGNI，当前仅 pglite + postgres 同一 schema
- 持久化 SQL / migration 变更
- Effect Application 在 delivery shell 落地的任何形式
- Capability Provider 契约改造 — `capability-boundary.ts` 已"实现即接口"
- Channel Port / Model Port / Repository Port 立项 —— 按 P5 YAGNI 等真需求

### 2.3 Hard boundaries

- 不引入第二数据库 schema
- Outbox 不改为通用领域事件总线
- Postgres 适配器**不再**持有第二 Run Engine / 第二 Policy Gate
- Capability Lease（path/domain/call/budget/fingerprint）不在本 PRD
- 模型走独立 Model Port（DESIGN §6.2），不混 Capability Provider

## 3. R2 Effect Tag 处置清单

### 3.1 仍被生产消费（5 个，本 PRD 必处理）

| Tag | consumer | 本 PRD 处置 |
| --- | --- | --- |
| `OutboxService` | `packages/adapters/src/postgres/postgres-outbox.ts` | 新增 `core/outbox.ts`，postgres 切到新接口后归档此 Tag |
| `EventStoreService` | `packages/adapters/src/postgres/postgres-event-store.ts` | 调和现有 `core/event-store.ts`（见 §5 CP-1）；postgres 切窄接口后归档此宽类 |
| `SnapshotService` | `packages/adapters/src/postgres/postgres-snapshot.ts` | 新增 `core/snapshot.ts`，切换后归档 |
| `ProjectionService` | `packages/adapters/src/postgres/postgres-projection.ts` | 新增 `core/projection.ts`，切换后归档 |
| `Config` | `packages/config/src/index.ts` | 移除 Tag 依赖，走 `process.env` 直读 + zod 校验（见 §5 CP-2） |

### 3.2 未被生产消费（9 个，本 PRD §4.4 一次性归档）

R11.2 grep 实证零生产引用：

- `LLMService` / `ToolExecutor` / `LoopInterrupt`
- `GuardService`（含 `[G-9]`/`[G-10]`，AGENTS §10 与 butler-v5 §0 均注明是开发守卫，非 runtime）
- `WeChatGateway` / `MCPDiscovery`
- `ProjectService` / `MemoryService`（含 `dream` —— DESIGN §12 明文"当前不建设"）
- `WorkflowService`（DESIGN §2 "不为未来规模预建通用 Workflow DAG"）

归档前再跑一次 `grep -RIn '@butler/ports' butler-v5/{packages,apps,cli}` 确认零命中再删。

## 4. 实施阶段

### Phase 1 — Inventory（**本班已完成**）

`grep -RInE 'LLMService|ToolExecutor|EventStoreService|OutboxService|SnapshotService|ProjectionService|Config'` 在 `butler-v5/{packages,apps,cli}` 拿到 5 处命中（§3.1）。

### Phase 2 — 新增 Core Ports（TDD）

| 新文件 | 测试 | 备注 |
| --- | --- | --- |
| `packages/ports/src/core/outbox.ts` | `outbox.test.ts` ≥3 例（接口形状 / null 路径 / 错误路径） | 工厂函数 `makeOutboxAdapter(persistence)` |
| `packages/ports/src/core/snapshot.ts` | 同上 ≥3 例 | |
| `packages/ports/src/core/projection.ts` | 同上 ≥3 例 | |
| `packages/ports/package.json` 增 `./core/{outbox,snapshot,projection}.js` exports | — | 与 `clock`/`credential-provider`/`event-store` 同形式 |

每端口 3 测试 × 3 端口 = +9 测试预期。

### Phase 3 — Postgres 适配器迁移

按依赖顺序：

| 子步 | 改造 | 兼容 |
| --- | --- | --- |
| 3a | `postgres-outbox.ts` import `OutboxPort` from `@butler/ports/core/outbox.js`；旧 `Layer.succeed(OutboxService as never, …)` 改为新 Port | `OutboxService` 仍保留（标 `@deprecated`），不破现有 unit test |
| 3b | `postgres-snapshot.ts` 同上 | |
| 3c | `postgres-projection.ts` 同上 | |
| 3d | EventStore 调和（见 §5 CP-1）；postgres-event-store.ts 切到窄 `EventStorePort`；宽订阅逻辑下沉为 postgres 自管 Stream helper | |
| 3e | `packages/config/src/index.ts` 移除 `Config` Tag import；改为 zod schema + `process.env` 直读（见 §5 CP-2） | |

每个子步一个原子 commit；旧 Tag 标 `@deprecated` 但**不删**直到 Phase 4。

### Phase 4 — 归档 9 个未消费 Tag（见 §5 CP-3）

`git mv` 整文件 `packages/ports/src/index.ts` → `_archive/packages/ports-effect-tag-scaffold/index.ts`（沿用 R10 monorepo convergence 路径）。

`ports/src/index.ts` 改写为薄 barrel：**仅** `export * from "./core/{clock,credential-provider,event-store,outbox,snapshot,projection}.js"`。deprecation 注释保留以便历史追溯。

### Phase 5 — 验证

```bash
cd butler-v5
CI= pnpm typecheck
CI= pnpm lint
CI= pnpm test            # 期望 ≥1004 pass / 1 skip / 0 fail（基线 +9 新测试）
CI= pnpm test:archived   # 19 文件 83 测试不回归
```

### Phase 6 — 文档同步

- `packages/ports/port-catalog.md`：§2 删除整个 R2 迁移看板；§1 加 outbox/snapshot/projection 物化条目
- `butler-v5/DESIGN.md` §7.1 状态表新增 3 行（outbox ✅ / snapshot ✅ / projection ✅），R2 总线行改"已归档 2026-08-XX"
- `tests/architecture/package-membership.test.ts` 第 (4) 测试改写：移走期望变为"不存在 → 0 match"，但**保留测试作 reminder** 待真正删 Tag 时再删测试
- `.blackboard/state.md` 顶部段 + "## 上一班" 增加 R12 班段

### Phase 7 — host 端复核

operator 在非 AI 沙箱的 terminal 跑：
```bash
cd butler-v5 && CI= pnpm test
pnpm smoke:allowlist-owner         # 真实 postgres 调一遍 owner 路径
```

期望：CI= pnpm test 全绿；smoke PASS。

## 5. Owner Review Checkpoints（待 operator 拍板）

### CP-1：EventStore 端口的形状选择

当前 `core/event-store.ts`（R10）有意比 R2 `EventStoreService` 窄：
- `EventStorePort` 现在：`append(streamId, events)` / `load(streamId)` — 基础两件
- `EventStoreService` 多了：`subscribe()` Stream / `nextVersion` — `postgres-event-store.ts:19` 注释明确写"intentionally narrower than R2 EventStoreService"

选项：
- **(a) 扩展 `EventStorePort`** 使其覆盖 subscribe/nextVersion → postgres 全切，调用方不变
- **(b) 保留 `EventStorePort` 窄** + postgres 自管 Stream helper（8–12 行代码）
- **(c) 拆分端口**：`EventStoreReadPort` / `EventStoreWritePort` / `EventStoreSubscribePort`（与 capability-boundary "一能力一端口" 风格一致）

**推荐 (a) 起步**；CP-1 不应拖延 Phase 2（Phase 2 不动 event-store）。

### CP-2：Config 迁移方向

`Config` Tag（AppConfig 形态：`{loop,guards,llm,db,wechat}`）vs 直接 env 读取。当前 `packages/config/src/index.ts` 仍 import 此 Tag。

选项：
- **(a) 纯 env 直读**：`process.env.BUTLER_V5_X` 分散读取，无 AppConfig 容器
- **(b) AppConfig-like 容器**：取消 Tag，改为 `function loadConfig(env): AppConfig` 调用方按需
- **(c) zod 全 schema 化**：所有 env 读经 zod 解析 → 默认值 + 验证 + 类型

**推荐 (c)** —— 与 DESIGN §3 信任边界验证 + AGENTS §3 一致；额外 + `BUTLER_V5_REQUIRED_ENV` 列出必设项。

### CP-3：9 个未消费 Tag 的归档策略

- **(a) 单 `git mv` 整文件**：保持原文 + 一次性迁移
- **(b) 拆文件迁**：每个 Tag 一个 `_archive/.../<tag>.ts`
- **(c) 直接删**：不归档，靠 git history

**推荐 (a)** —— 与 R10 monorepo convergence 收尾方式一致；保留原文便于追溯；最少 churn。

### CP-4：包归属

新 `/core/*` 端口放 `packages/ports/src/core/`（与现有 clock/credential-provider/event-store 同位）。
**默认采纳**（与 R11.2 路径一致）；本 checkpoint 仅记为已闭。

## 6. 不在本 PRD（明示）

- Channel Port / Model Port 立项
- Repository Port 第二实现 trigger
- Effect Application 在 runtime 落地
- Capability 契约改造
- `ports-effect-tag-scaffold/` 目录的二次归档或删除
- 新 v5 承重文件保护清单扩展

## 7. 风险与回滚

### 风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| CP-1 选错扩散 | 所有 run-engine / event-bridge 调用方 | Phase 3d 单 commit，可独立 revert |
| Phase 3e Config 迁移 | 启动路径 | smoke `allowlist-owner` 必跑 |
| Phase 4 归档漏 grep 命中 | 运行时崩溃 | 归档前最终 grep + `--no-verify` 跳 pre-commit + 立即 host 跑测试 |
| capability-boundary 误改 | 不在本 PRD 范围 | 文件不动 |

### 回滚

每 Phase 1 commit 可独立 `git revert`。建议分支策略：单 commit per phase，PR 形式，方便逐 phase 回退。

### Operator 复核清单

- Phase 2 新文件 owner review（接口形状、命名风格）
- Phase 3 每迁移 owner review（postgres 行为不变性）
- Phase 4 归档前最后一次 grep 验证
- Phase 7 host terminal 全 gate 通过

## 8. 不要做（重申）

- 不复用 `_archive/packages/{application,infrastructure,contracts}`
- 不为 Channel/Model/Repository 立新 Port（P5 YAGNI）
- 不动受保护 AI 守卫 / `.claude/settings.json` / AGENTS.md（除 `[MANUAL-OVERRIDE]`）
- 不为本次迁移改 Capability 契约或 Run Engine 入口
- 不为"架构完整"造休眠接口（DESIGN §7）

## 9. 验收（本 PRD 完成判定）

- [ ] 3 新增 Core Port（outbox/snapshot/projection）+ tests 绿（≥+9 测试）
- [ ] postgres 适配器 4 处 import 切到新 Port + EventStore 调和完成
- [ ] `packages/config/src/index.ts` Config Tag 依赖去除
- [ ] 9 个未消费 R2 Tag 类归档到 `_archive/packages/ports-effect-tag-scaffold/`
- [ ] `packages/ports/src/index.ts` 薄 barrel 化（仅 `export * from "./core/*"`）
- [ ] `port-catalog.md` / `DESIGN §7.1` / `package-membership.test.ts` 同步更新
- [ ] `state.md` 顶部段 + "## 上一班" 新增 R12 班段
- [ ] typecheck 0 错 / lint 0 警告 / `CI= pnpm test` ≥ 基线 +9
- [ ] operator host terminal 复核 + `pnpm smoke:allowlist-owner` 一轮 PASS
