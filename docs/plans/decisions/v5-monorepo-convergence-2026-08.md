---
status: done
date: 2026-08-27
stakeholders: owner + butler-v5 engineering
scope: butler-v5/packages
related_design:
  - butler-v5/DESIGN.md#17 仓库管理与工程形态（monorepo）
  - butler-v5/DESIGN.md#7 Ports（端口，依赖方向向内的接口）
  - butler-v5/DESIGN.md#20 架构不变量（UI-16 monorepo 收敛）
---

# v5 monorepo 收敛整改计划（2026-08）

## 1. 背景：代码交付与目标架构的对齐差距

代码改造的主体已对齐 DESIGN（单一 Run Engine + Policy Gate + 副作用出口、六边形依赖方向、单
一 schema、P3 两条接缝、P4 不引入第二套状态机）。**唯一未对齐的是 DESIGN §17 的
monorepo 工程收敛**：三个「未接线脚手架」包仍在并继续被编译、被覆盖率与 `test:archived`
扫描，未达到「移入 `_archive/` 或删除，不在编译与测试白名单中」的终态。

现状证据（2026-08-27 核对）：

| 包 | 生产消费者 | 生产代码状态 | 在测试/覆盖率中 |
| --- | --- | --- | --- |
| `packages/application` | 无（apps/runtime 均不 import） | `src/index.ts` 空壳 `export {}`；脚手架在包内 `_archive/` | 是（coverage.include + test:archived） |
| `packages/infrastructure` | 无 | `src/index.ts` 反 re-export 一整套 `_archive/*`（guards/persistence/eventstore/llm/wechat/mcp/acl） | 是（coverage.include + test:archived） |
| `packages/contracts` | 无 | `src/index.ts` export api/events/plugin；本身 **反向 import `@butler/domain`**（违反「port 带不依赖 core」） | 是（test:archived） |

根 `tests/{guard,architecture}` 已有 `unwired-packages-archived`、`no-layer-violation`、
`apps-layer-boundaries` 等在守护收敛方向——**说明代码已按收敛前进，但最后一步「包级别清理 +
配置/白名单同步」未执行。**

## 2. 整改目标（对齐 DESIGN §17.3 + 不变量 16）

1. 三个未接线包不再作为「主线包」编译、测试、计覆盖率；
2. 不删除有价值历史/测试资产，但不允许其留在生产黑白名单中；
3. 依赖方向干净：port 带不反向依赖 core（修 `contracts` 的方向问题）；
4. 工程门禁（`pnpm test` / `pnpm gate` / coverage）反映目标架构的测试真相。

## 3. 整改方案（推荐）

### 3.1 归档落位

采用「**包 ← 根级 `_archive/`**」统一落位，消除 `src` 反 re-export 的中间态：

- **删除** `packages/application`、`packages/infrastructure`、`packages/contracts` 三个包目录；
- 将三者有价值资产迁至根级 `_archive/` 下保留：
  - `_archive/packages/application/`（含 `_archive/run-loop`、`delegate-task`、`dream`、`run-workflow` 及测试）
  - `_archive/packages/infrastructure/`（guards/persistence/llm/wechat/mcp/acl/shadow/patch/migration/layers）
  - `_archive/packages/contracts/`（api/events/plugin + 测试）
- 根 `_archive/` 整体 `exclude` 出 vitest/eslint/tsconfig/turbo（见 §3.2），与 DESIGN「不在编译与测试白名单」一致。

> 可选替代（如果 owner 不想物理移文件）：保留包目录但把整包 `src` 清成空壳 + 从所有白名单剔除。
> 本计划按前一种（确定性更强）起草。

### 3.2 配置/白名单同步

| 文件 | 改动 |
| --- | --- |
| `butler-v5/vitest.config.ts` | coverage.include 移除 `packages/application/src`、`packages/infrastructure/src`；增加 `exclude: "**/_archive/**"`（防根级扫描）；如保证不扫 `_archive`，`packages/contracts` 的 exclude 可保留 |
| `butler-v5/package.json` | `test:archived` 指向根 `_archive/packages/*` 与对应测试；`test`（coverage）不再含三包 |
| `butler-v5/tsconfig.json` / 各 `packages/*/tsconfig.json` | 根级 `_archive/**` 从 include/exclude 剔除 |
| `butler-v5/turbo.json` | 若用 package 过滤，从 pipeline 去掉三包 |
| `butler-v5/.eslintrc.json` | 已有 `packages/**/_archive/**` ignore，追加根 `_archive/**` |
| `scripts/run-test-layer.sh` | 移除 `application/src`、`infrastructure/src` 的测试分支 |
| `tests/architecture/*` | 校准：`apps-layer-boundaries` 的 `infrastructure/_archive/persistence/schema` 特殊豁免、`dependency-direction` 的 `application/src` 扫描、`no-layer-violation` 的 infrastructure 分支，改为指向根 `_archive` 或删除 |
| `pytest`（butler-v5 为 TS，但若引用 contracts 的 python 事件，见 §3.3 注） | 保持现状，`_archive` exclude |

### 3.3 依赖方向修正（`contracts` 反向 import）

`packages/contracts/events.ts` 反向 `import type { EventEnvelope, StreamType } from "@butler/domain"`。
收敛后落位 `_archive`，该问题随包移出而消失；**不单独重构**。若未来需要「契约事件类型」，
应按 DESIGN §7 由 `domain` 导出类型、port 只引用 domain，而非独立 core 消费型包。

> 注：AGENTS.md 中「EventType 须用 butler/contracts/events.py」指 **v4 Python** 侧的历史约定，
> 与本 TS `packages/contracts` 无关，不在此计划范围内。

### 3.4 validation（整改完成门禁）

1. `pnpm typecheck` 通过，且不再编译三包；
2. `pnpm test`（coverage）通过，覆盖率只统计生产接线包，三包不计入；
3. `pnpm test:archived` 仍能跑 `_archive` 资产测试（历史保护）；
4. `pnpm lint`、`pnpm format:check` 通过；
5. 架构守卫测试（`unwired-packages-archived` 等）更新后通过；
6. `scripts/typecheck-gate.sh` 通过。

## 4. 落地步骤（顺序）

1. **基线**：跑 `pnpm test` + `pnpm gate` 记录三包当前测试数（防误删回归）。
2. **物理迁移**：`application/infrastructure/contracts` → 根 `_archive/packages/*`（保持内部相对路径）。
3. **删包**：从 `pnpm-workspace.yaml` 去掉三包；删三个 `packages/*/package.json`。
4. **白名单同步**：改 vitest/tsconfig/turbo/eslint/run-test-layer/架构测试（§3.2）。
5. **修测试豁免**：按 §3.2 更新指向根 `_archive` 的断言。
6. **收口验证**：跑 §3.4 全部门禁；修正失败项。
7. **文档同步**：production-architecture 更新包结构；state.md 记一行；本篇标记 `status: done` 归档到 `docs/plans/decisions/`。

## 5. 风险与处置

| 风险 | 处置 |
| --- | --- |
| 部分 `_archive` 被 apps/persistence 间接引用 | 迁移前 grep 全仓，先收拢引用再移；若确有接线，改列入「保留包」 |
| 根 `_archive` 被 vitest include `packages/**` 兜住 | 用显式 `exclude: "**/_archive/**"`；必要时把 include 收窄到 `packages/*/src` |
| coverage 阈值因减仓而变 | 复核阈值是否仍 ≥60/70/70；若三包拉高虚假达标，减仓后反映真实基线，阈值保留即可 |

## 6. 非目标

- 不改生产 Loop / Trigger / Capability / schema；
- 不新增或重命名已接线包；
- 本轮不处理 `packages/migration`（其源在 src，符合 §17 targeting「保留 migration 包收敛到单一 persistence」——v5 已收敛为保留 `migration` 包且 `persistence/migrations` 不存在，二选一已定）；
- 不重构 `_archive` 内部逻辑（仅归档保留）。

## 7. 验收口径（Definition of Done）

- `butler-v5/` 下不存在 `application`/`infrastructure`/`contracts` 三个包；
- 三个包的产物进入根 `_archive/` 且不参与 compile/test/coverage；
- `pnpm test`（coverage）、`pnpm gate`、`typecheck-gate` 全部绿灯；
- `test:archived` 能命中原 `_archive` 资产测试；
- production-architecture 与 state.md 已同步；
- 本篇合入 `docs/plans/decisions/` 作决策记录。