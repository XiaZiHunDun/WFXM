# Phase 2 · T1 测试清理记录（2026-11-19）

> 对应任务书：[`phase2-test-eval-system-2026-11-19.md`](./phase2-test-eval-system-2026-11-19.md) §2 / §9 T1
> 本文件记录：section 守卫的映射与删除清单、命令测试合并方式、发现的缺陷与覆盖缺口。
> 生产代码零改动。

## 1. 结构不变量：24 → 0 个 `section*` 文件

原 24 个章节守卫（4606 行）全部删除；其中有价值的结构约束已并入 8 个不变量文件。
不变量文件本身不新增依赖，全部可离线运行。

| 原文件 | 去向 / 处理 |
|--------|-------------|
| `section3-dependency-rules` | #1/#4 → `dependency-direction.test.ts`（含相对路径写法、policy-gate SDK 隔离）；#2/#3/#6 → `apps-layer-boundaries.test.ts`；#5 → `side-effect-throat.test.ts` |
| `section5-domain-pure` | → `domain-zero-io.test.ts`（域层零项目依赖、零 Node 内置） |
| `section6-application-orchestrator` | RunEngine 唯一声明 → `side-effect-throat.test.ts` |
| `section7-ports-main` / `7-1-model-port` / `7-1-port-snapshot` / `7-1-repository` | 依赖方向 → `dependency-direction.test.ts`；Model Port / Repository 行为由 `packages/ports/src/core/model-port.test.ts`、`runtime-store.cross-impl.test.ts` 等功能测试覆盖。`r2-shim` 生产引用检查由 §15 超时守卫间接保留（生产文件不得 import）。 |
| `section8-9-adapters-boundary` | TriggerSource/builders 由 `packages/domain/src/runtime/run-trigger.test.ts` 覆盖；“Model/Channel 不得注册为 Capability” → `capability-no-auto-grant.test.ts` |
| `section10-governance-arch-guard` | 行为由 `policy-gate.test.ts`、`capability-boundary.test.ts` 覆盖；ACK 文本字段形状不再守卫（见 §3 缺口） |
| `section10-4-6-13-deep-audit` | ModelDecision 5 tag 由 `decision` 功能测试覆盖；sandbox profile 字段形状不守卫（见 §3） |
| `section11-deferred-triggered` / `11-1-2-3-current-state-immutable` | 表存在性/路由计数属实现形状，功能由 task/document/procedure store 测试覆盖；删除（见 §3） |
| `section12-knowledge-memory` | 三层/去重/自动晋升/候选过期均有领域功能测试覆盖；表字段形状不守卫（见 §3） |
| `section14-token-cost` / `14-observability-fields` / `14-costusd` | 计费与 trace 行为由 `apps/api/src/llm-pricing.test.ts`、`packages/domain/src/observability/local-trace.test.ts` 覆盖；字段形状不守卫（见 §3） |
| `section15-effect-discipline` | → `single-llm-tool-loop.test.ts`（`completeWithTimeout`、直连调用必须有超时、adapter 不自带超时策略） |
| `section16-process-boundary` | → `workspace-sandbox-arch.test.ts`（子进程运行器不得 import Core） |
| `section17-1-2-monorepo-management` / `17-3-orphan-package` | → `package-membership.test.ts`（无孤儿包、恰好 5 个活跃包） |
| `section18-trigger` | 未触发特性守卫删除（见 §3） |
| `section20-invariants-batch-a` | #1 → `side-effect-throat.test.ts`；#2/#3/#4 → `dependency-direction.test.ts` + `apps-layer-boundaries.test.ts` |
| `section20-invariants-batch-b` | #6/#13 行为由 `run-engine.test.ts`、`wechat-active-run-conflict.test.ts` 覆盖；#15 为一次性交接决策，删除 |

### 额外删除（非 section，但已失效/重复）

| 文件 | 行数 | 理由 |
|------|------|------|
| `tests/guard/no-layer-violation.test.ts` | 178 | 与 `dependency-direction.test.ts` 重复且更弱（只查 `@butler/*` 字符串） |
| `tests/architecture/r2..r6-end-to-end.test.ts` | 205 | 5 个文件已被 `vitest.config.ts` exclude，从未在任何 CI 中执行；同步移除 exclude 条目 |
| `apps/api/src/wechat-inbound-commands.test.ts` / `wechat-memory-commands.test.ts` / `wechat-subagent-commands.test.ts` | 534 | 合并进 `apps/api/src/wechat-commands.test.ts`（共享 `tests/wechat-command-harness.ts`），并删除 2 条与 `wechat-quality-gate.test.ts` 重复的 /验 用例 |

保留：`wechat-task-commands.test.ts`（任务生命周期）、`wechat-undo-command.chain.test.ts`（撤销链）。
两者是独立子系统而非样板重复，强行并入会突破「单文件 ≤400 行」约束。

## 2. 数量变化

| 指标 | 清理前 | 清理后 | 变化 |
|------|--------|--------|------|
| 测试文件 | 314 | 282 | -32 |
| 测试行数 | 47,302 | 42,356 | -4,946（-10.5%） |
| `tests/architecture/section*` | 24 文件 / 4,606 行 | 0 | -100% |
| 命令测试样板 | 5 文件 / 1,352 行 | 3 文件 / 1,076 行 | -276 |

整体降幅 10.5%，未达任务书的 15%。剩余降幅依赖 T2–T5 用契约/集成套件替换重叠的旧断言，
不再为凑数字删除仍有语义的用例（任务书 §9「禁止为了绿而放宽断言」）。

## 3. 发现的缺陷与覆盖缺口

### F-01 LLM 调用缺少单次超时（记录，不在本任务修）

`apps/api/src/butler-assembly.ts` 的 `createButlerModelPort` 直接
`Effect.runPromise(adapter.complete(...))`，没有 `Effect.timeout`。
pi 引擎只在任务级设置 abort 定时器，单次模型调用可能长时间挂起。
`single-llm-tool-loop.test.ts` 暂以 `KNOWN_UNBOUNDED` 白名单放行并指向本条。

### 已移除、暂无等价静态守卫的约束（靠功能测试或产品决策兜底）

| 约束 | 为何移除 | 现在的兜底 |
|------|----------|------------|
| §11 表存在性（tasks/procedures/documents）、无 approvals 表 | 断言 schema 形状，重构即误报 | task/document/procedure store 功能测试 |
| §12 DurableMemory 四字段、无 embedding 列 | 同上 | `knowledge/*.test.ts` |
| §14 TraceEvent / LLMUsage 字段形状 | 同上 | `llm-pricing.test.ts`、`local-trace.test.ts` |
| §10 PolicyDecision / ActionRequest / ScopedGrant 字段清单 | 同上 | `policy-gate.test.ts`、`capability-boundary.test.ts` |
| §18 未触发特性（projection/embedding/snapshot）不得被引用 | 属产品触发决策，功能上线时必然失败 | 发布评审；如需恢复应改为「触发器检查清单」而非测试 |
| §0「不存在进程内 EventBus」 | 一次性架构决策 | code review |
