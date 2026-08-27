# Butler v5 布局收敛计划（六边形落地）

> **状态**：✅ 主体完成。S1.4 收敛评估、S2 端口承载位次均已于 2026-08-26 收口。
> **目标架构**：[`../../../butler-v5/DESIGN.md`](../../../butler-v5/DESIGN.md) §1–§20
> **架构事实**：[`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)
> **产品边界**：[`v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md)
> **日期**：2026-08-26

## 1. 目的

把 DESIGN.md 的六边形目标形态落到真实仓库：**依赖方向单向向内核、单一 schema、脚手架修剪、架构测试锁死**。不破坏现有微信生产路径与既有测试基线（`pnpm test` 913 pass）。

## 2. 决策（Owner 已确认）

1. **Core 全端口化**：现在就做，不做保守版（仅 S1/S2/S4）。
2. **归档方式**：`_archive/` 软归档（移目录 + workspace 忽略），保留 git 历史；不物理删除有价值代码。
3. **端口承载**：统一收进既有 `packages/ports` 包（托管 Repository / Model / Capability / Channel / Clock 接口），对齐 DESIGN §17。⚠️ `packages/ports/src/index.ts` 是受保护文件，改其接口需 `[MANUAL-OVERRIDE]` 或经人工覆盖流程。
4. **执行节奏**：按 S1 → S2 → S3 → S4 → S5 推进，每阶段独立绿 + 可回滚。

## 3. 勘察事实（2026-08-26）

- `packages/application`：`src/index.ts` 为 stub（`export {}`）；真代码在 `_archive/`。**无生产消费者**。
- `packages/infrastructure`：`src/index.ts` re-export `_archive/*` Effect Layer；`src/layers.ts` 组合示例；`src/migration/v4-to-v5.ts` 为**真实迁移工具**。**无生产消费者**。
- 既存测试引用脚手架包：`tests/guard/no-layer-violation.test.ts`、`tests/guard/meta-audit.test.ts`、`tests/architecture/apps-layer-boundaries.test.ts`、`tests/contracts/*`。清理须连带核对。
- `packages/migration`：真实迁移/影子运行器（pipeline、shadow-runner、v4-source），**非死代码**。
- `apps/wechat-gateway`：无 `package.json`、无 `src`，纯残留，workspace 不识别，删除安全。
- 生产链 = `apps/api → packages/runtime + packages/persistence + packages/adapters`；`runtime` 当前直接依赖 concrete `persistence`。

## 4. 阶段 S1 — 脚手架清理（低风险）

**目标**：把"生产集 vs 未接线脚手架"收成一条清晰线，零行为变化。

1. `apps/wechat-gateway`：删除残留目录（无 package.json）。
2. `packages/application`、`packages/infrastructure`：确认无生产 import；从 `pnpm build`/默认 test 排除，保留 `_archive/` 历史（若需）。
3. 连带核对并更新 `tests/guard/*`、`tests/architecture/*` 中对脚手架包的引用，避免误读/误删。
4. 澄清 `config`、`contracts`、`shared`：保留被生产 import 的部分；`migration` 包与 `infrastructure/src/migration`、`persistence/migrations` 收敛策略单列评估。

**验证**：`pnpm test` / `pnpm build` / `pnpm typecheck` 全绿；`ts-prune` 无生产引用被删。

## 5. 阶段 S2 — 端口接口奠基（增量，先立语义）

1. 在 `packages/ports` 定义 **Repository / Model / Capability / Channel / Clock** 端口接口，空壳指向现有实现。
2. 不改变生产 import 方向，纯新增类型；`pnpm typecheck` 绿。
3. 若触及受保护 `ports/src/index.ts` → 标记 `[MANUAL-OVERRIDE]`。

## 6. 阶段 S3 — Core 全端口化（高风险，分 slice）

**目标**：runtime/domain 不再 import 具体适配器，统一经端口接口由 `wiring.ts` 组合根注入。

- slice 顺序建议（每 slice 一个边界 + 测试绿，失败随时回滚）：
  1. ScopedGrant 服务
  2. RunEngine 的 persistence 访问（Repository 端口）
  3. PolicyGate
  4. 工具执行（Capability 端口）
  5. LLM 调用（Model 端口）
- 原则：接口适配不改行为、仅改依赖方向；组合根 `apps/api/src/wiring.ts` 注入实现；live 微信（gateway）只在整体绿后再升版。

**验证**：每 slice 后 `pnpm test` 绿 + `scripts/typecheck-gate.sh` 绿。

## 7. 阶段 S4 — 架构测试锁死

新 vitest 架构测试：
- `runtime` / `domain` 不得 import `persistence` / `adapters` 具体实现；
- `apps/*` 不得直接读写具体 schema（仅经 repository/接口）；
- 所有副作用工具执行必须过 Capability Boundary；
- 生产包禁止 `import *`。

接入 `pnpm gate` 与 CI；验证能抓到故意违规，且既有 913 测试不回退。

## 8. 阶段 S5 — 文档与守卫收口

1. 同步生产架构文档 §7（包处置：application/infrastructure 已归档、单一 schema、ports 承载接口）。
2. 审核 `scripts/ai_guard/*.py` 受保护文件清单 / PreToolUse hook 是否引用已归档包；需改 → 人工覆盖。
3. 根 `AGENTS.md`、`docs/AGENTS.md`、`.cursorrules` 与新架构对齐。

## 9. 风险与守门

- 受保护文件（`packages/ports/src/index.ts`、`packages/domain/src/errors.ts`、AGENTS、ai_guard、`.cursorrules`）触及即走人工/`[MANUAL-OVERRIDE]`。
- 每阶段独立绿 + 可回滚；不一次性大重构。
- 生产稳定性优先：接口适配不改行为，live 只在整体绿后升版。

## 10. 执行记录（2026-08-26 晚 · S3 完成）

勘察修正了 S3 的规模假设：Core 本已高度端口化（`run-engine`/`policy-gate`/`scoped-grant`/`capability-boundary` 均依赖 domain `RuntimeStore` 等抽象接口注入），**运行时唯一的 concrete 泄漏是 `packages/runtime/src/bridge.ts`**。

- **S3 已做**：
  - domain 新增 `EventStorePort`（`packages/domain/src/runtime/event-store-port.ts`，从 `@butler/domain/runtime.js` 导出）。
  - `EventBridge` 迁入 `packages/persistence/src/event-bridge.ts`，`implements EventStorePort`，新增子路径导出；删除 runtime `bridge.ts` 与 index re-export。
  - `agent-kernel.ts` / `delegate-runtime.ts` 改依赖 `EventStorePort`；runtime `package.json` 移除 persistence 生产依赖（转 devDeps）。
  - apps/api（27 文件）、migration、adapters import 从 `@butler/runtime/bridge.js` → `@butler/persistence/event-bridge.js`。
  - typecheck 全绿；基线测试 916 pass（仅 postgres 实连 + bubblewrap slirp 两个环境耦合失败，与改前一致）。
- **S4（锁）已加**：`tests/architecture/dependency-direction.test.ts` 新增 "runtime(Core) 不得 import persistence/adapters/config/infrastructure/application"，pass 5 项。
- **S1**：`apps/wechat-gateway` 已不存在；`unwired-packages-archived.test.ts` 已 pass（scaffold 即视为归档）。application/infrastructure 的 build/test 排除可按后续清理。
- **S5 已完成（2026-08-26）**：生产架构文档 §7 更新（persistence 承载 EventBridge / 单一 schema）；`pre_tool_use_hook.py`、`pre_commit_hook.sh`、`.cursorrules` 承重清单已把 `runtime/src/bridge.ts` → `persistence/src/event-bridge.ts`；两个守卫脚本语法校验通过。

## 11. 收尾记录（2026-08-26 晚 · S1.4 + S2 收口）

**S1.4 收敛评估**（无代码变更，纯 Assess 结论）：
- `packages/config` / `contracts` / `shared` **无任何生产包 import**（唯一消费是 scaffold 的 `infrastructure/src/layers.ts`）→ 属未接线/测试/文档专用包，不在生产链；保留现状，不改动。
- Migration 收敛：**单一 schema = `packages/persistence/src/migrations/`**（0001–0010，含 registry 测试与 `run-migrations.ts`）；`packages/migration`（pipeline/shadow-runner/v4-source）为**独立迁移工具**，无运行时 import，standalone 使用；`packages/infrastructure/src/migration/v4-to-v5.ts` 为**未接线重复**，随 infra 脚手架归档，不视为 schema 来源。

**S2 端口承载位次**（对齐 DESIGN §7/§17）：`EventStorePort` 自 `@butler/domain/runtime.js` 迁移至 `@butler/ports/core/event-store.js`（DESIGN 要求 Ports 只依赖 domain 类型、Core 依赖 Ports）。做法：走 `packages/ports` 新子路径模块，**未触碰受保护 `src/index.ts`**；persistence 的 EventBridge、runtime 的 agent-kernel/delegate-runtime 改指端口；runtime/persistence 新增 `@butler/ports` 生产依赖；`pnpm install --no-frozen-lockfile` 重链。typecheck 全绿；测试 917 pass，仍仅 postgres 实连 + bubblewrap slirp 两个环境耦合失败。