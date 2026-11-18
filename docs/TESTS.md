# Butler v5 — Test Coverage Inventory

> **生成日期**: 2026-09-22 | **更新**: 2026-11-18（v4 退役后只保留 v5 测试） | **读者**: Owner / Contributor / 审稿人
> **关系**:
> - 功能视角 → [`FEATURES.md`](FEATURES.md)
> - HTTP/WS API → [`API_ENDPOINTS.md`](API_ENDPOINTS.md)
> - env vars → [`ENV.md`](ENV.md)
> - 目标架构（§3–§20 invariants 锁源）→ [`../DESIGN.md`](../DESIGN.md)
> - 当前实现与第一阶段验收 → [`architecture/wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html)
> - 自托管指南（冒烟验收）→ [`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md)
> - Agent 入口 → [`../AGENTS.md`](../AGENTS.md)

---

## 图例

- ✅ **已 ship**（CI 跑绿 + 守门齐全）
- 🟡 **已 ship 子集**（核心 pass，外延未完）
- 📅 **延后 / PRE-EXISTING**（已知 carry；D-series 共识不修）

## §0 总览

| 类别 | 目录 | test 文件数 | 状态 |
|------|------|------------|------|
| Architecture（§3–§20 invariants） | `tests/architecture/` | **46** | ✅ |
| Acceptance（harness + realistic + regression + subagent + audit-state + fault-tolerance + commands-approval + methodology） | `tests/acceptance/` | **7** | ✅ |
| E2E（r7-wiring + r8-real-persistence） | `tests/e2e/` | **2** | ✅ |
| Contracts（port stability） | `tests/contracts/` | **1** | ✅ |
| Eval（harness + scenarios + mock-llm） | `tests/eval/` | **22** | ✅ |
| Guard（no-layer-violation） | `tests/guard/` | **1** | ✅ |
| _meta（typed-rules + unique-list） | `tests/_meta/` | **2** | ✅ |
| Inline unit（apps/api/src + packages/*/src + cli/src） | 与源码同目录 | **233** | ✅ |
| **Total test files** | — | **314** | 见 §1–§5 |

> **数法说明**：按 `find . -name "*.test.ts"` 统计；`owner-routes-source.ts` 等非测试辅助文件不计入。

## §1 分层验证（L1–L4）

| 层 | 范围 | 命令 |
| --- | --- | --- |
| L1 | 单元 / 契约 | `pnpm test` |
| L2 | 消息出口规范化 | `pnpm vitest run packages/runtime/src/butler/presentation.test.ts` |
| L3 | 评估场景（gate） | `pnpm vitest run tests/eval` |
| L4 | 渠道前验收窗口（真实路由 + 真实 runtime） | `npx tsx scripts/l4-smoke.ts` |
| L4 可靠性 | 重投 / 并发 / 连续投递 / 无待审批 | `npx tsx scripts/l4-smoke.ts --suite reliability` |

L4 脚本要求网关已启动，并从 `~/.config/env` 读取 `BUTLER_V5_INBOUND_SHARED_SECRET`。

## §2 Architecture Tests（46 files / §3–§20 invariants）

> DESIGN §20 不变量 → 每个 arch test 锁 1 条；`section*-*.test.ts` 命名约定。命令：`pnpm vitest run tests/architecture`。

### §2.1 依赖方向 & Core 不变量（§3）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `dependency-direction.test.ts` | 依赖方向向内核 | ✅ |
| `section3-dependency-rules.test.ts` | §3 #1–#6 全 6 cases | ✅ |
| `domain-zero-io.test.ts` | Domain 零 I/O（§5） | ✅ |
| `section5-domain-pure.test.ts` | Domain pure 函数 8 cases | ✅ |
| `single-llm-tool-loop.test.ts` | 单 LLM + tool 调用循环 | ✅ |
| `working-set-budget-no-delete.test.ts` | working-set 超预算只压缩不删（§6.1 / §20 #14） | ✅ |
| `three-memory-separation.test.ts` | 3 记忆层 cross-import = 0（§12 / §20 #9） | ✅ |

### §2.2 Application & Orchestrator（§6）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `section6-application-orchestrator.test.ts` | RunEngine 7 职责 + 5-tag ADT | ✅ |
| `r2-end-to-end.test.ts` | RunEngine E2E（plan → exec → finish） | ✅ |
| `r3-end-to-end.test.ts` | RunEngine + policy gate + audit | ✅ |
| `r4-end-to-end.test.ts` | RunEngine + approval flow | ✅ |
| `r5-end-to-end.test.ts` | RunEngine + waiting_external | ✅ |
| `r6-end-to-end.test.ts` | RunEngine + outbox + persistence | ✅ |
| `side-effect-throat.test.ts` | 所有副作用必经 canonical runButlerLoop（§3 #5） | ✅ |

### §2.3 Ports（§7）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `section7-ports-main.test.ts` | thin barrel + interface-only + 依赖向内 | ✅ |
| `section7-1-port-snapshot.test.ts` | v5 物化 Core Port 完整性 | ✅ |
| `section7-1-model-port.test.ts` | Model Port 物化 | ✅ |
| `section7-1-repository.test.ts` | Repository Port 物化 | ✅ |
| `mcp-contract.test.ts` | MCP thin client 契约 | ✅ |
| `mcp-spawn-arch.test.ts` | MCP spawn arch 边界 | ✅ |

### §2.4 Driving / Driven Adapters（§8–§9）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `section8-9-adapters-boundary.test.ts` | Trigger + Capability 边界 | ✅ |
| `apps-layer-boundaries.test.ts` | apps 不允许 `runTool*` 旁路 | ✅ |
| `capability-no-auto-grant.test.ts` | Capability 不自动 grant | ✅ |
| `workspace-sandbox-arch.test.ts` | workspace + sandbox arch | ✅ |

### §2.5 Governance（§10）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `section10-governance-arch-guard.test.ts` | §10 9 cases | ✅ |
| `section10-4-6-13-deep-audit.test.ts` | §10.4–6 + §13 10 cases deep audit | ✅ |
| `child-run-permission-not-wider.test.ts` | Child Run 不宽于父（§4.2 / §20 #5） | ✅ |
| `child-run-cancel-cascade.test.ts` | 父 cancel 级联 | ✅ |

### §2.6 Persistence（§11）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `section11-1-2-3-current-state-immutable.test.ts` | 7 cases（Current State + Append-only + Outbox） | ✅ |
| `section11-deferred-triggered.test.ts` | §11.4 trigger-conditioned | ✅ |
| `outbox-post-transactional.test.ts` | Outbox 事务原子性（§20 #8） | ✅ |
| `audit-event-tx-atomicity.test.ts` | `audit_events` 事务原子性（§11.2） | ✅ |

### §2.7 Knowledge & Memory（§12）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `section12-knowledge-memory.test.ts` | 3 层独立 + 6 cases | ✅ |

### §2.8 Observability（§14）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `section14-observability-fields.test.ts` | 14 fields 捕获 | ✅ |
| `section14-token-cost.test.ts` | 9 cases token 路径 | ✅ |
| `section14-costusd.test.ts` | 7 cases costUsd 路径 | ✅ |

### §2.9 Engineering / Process（§15–§17）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `section15-effect-discipline.test.ts` | Effect-TS 工程范式 | ✅ |
| `section16-process-boundary.test.ts` | 单进程模块化单体边界 | ✅ |
| `section17-1-2-monorepo-management.test.ts` | workspace glob + 5 active packages | ✅ |
| `package-membership.test.ts` | package 成员边界 | ✅ |

### §2.10 Trigger & Invariants（§18–§20）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `section18-trigger.test.ts` | §18 deferral trigger-条件未达 | ✅ |
| `section20-invariants-batch-a.test.ts` | §20 invariant 批次 A | ✅ |
| `section20-invariants-batch-b.test.ts` | §20 invariant 批次 B | ✅ |
| `section0-1-2-19-sweep.test.ts` | §0 + §1 + §2 + §19 sweep | ✅ |
| `p3-seam-guard.test.ts` | P3 seam 守护 | ✅ |

## §3 Acceptance Tests（7 files）

> `pnpm test:acceptance`；harness 启动生产 wiring + 内存 PGlite + 脚本化 fixture LLM。

| File | 类别 | 状态 |
|------|------|------|
| `acceptance/scenarios/realistic.test.ts` | 真实场景产品层行为（A/B/C/D/E 组） | ✅ |
| `acceptance/product-regressions.test.ts` | 微信产品层回归：/undo + spam guard + LLM tracer + inline-approval + run_command argv + P2 batch | ✅ |
| `acceptance/commands-approval.test.ts` | 命令 + approval 矩阵：/撤销 /重试 /确认 /拒绝 | ✅ |
| `acceptance/subagent-multiturn.test.ts` | subagent 多轮 | ✅ |
| `acceptance/fault-tolerance.test.ts` | fault tolerance：3 层自愈（G-8） | ✅ |
| `acceptance/audit-state.test.ts` | audit emit actor（currentOwnerActor） | ✅ |
| `acceptance/methodology.test.ts` | methodology 19·19（含 M15 docker-deploy） | ✅ |

### §3.1 Acceptance harness 支持

| File | 作用 |
|------|------|
| `acceptance/harness.ts` | `makeAcceptanceApp()` — 生产 wiring + 内存 PGlite + 脚本化 LLM |
| `acceptance/multi-round.ts` | N-round verify helper |
| `acceptance/methodology-index.ts` | methodology 索引 |
| `acceptance/scenarios/_fixtures.ts` | scenario fixtures |
| `acceptance/scenarios/recordings/` | per-scenario expected fixtures |

## §4 E2E / Contracts / Eval / Guard / _meta

```bash
pnpm vitest run tests/e2e
pnpm vitest run tests/contracts
pnpm vitest run tests/eval
pnpm vitest run tests/guard
pnpm vitest run tests/_meta
```

| 目录 | 文件 | 作用 | 状态 |
|------|------|------|------|
| `e2e/` | `r7-wiring.e2e.test.ts` | apps/api wiring + Channel Port 注入 + iLink fallback | ✅ |
| `e2e/` | `r8-real-persistence.e2e.test.ts` | 真 Postgres 路径（pglite + Drizzle） | ✅ |
| `contracts/` | `test_port_stability.test.ts` | Port 契约稳定（`EXPECTED_EXPORTS` / `EXPECTED_PORT_FILES`） | ✅ |
| `eval/` | `harness.ts` / `metrics.ts` / `mock-llm-scripted.ts` / `scenarios/*.test.ts` | Model Port 与 LLM eval 工具集（10 个流程场景） | ✅ |
| `guard/` | `no-layer-violation.test.ts` | 无 layer 违规（§3 依赖方向硬规则） | ✅ |
| `_meta/` | `architecture-typed-rules.test.ts` / `list-unique-test-files.test.ts` | 守护 architecture test 规则与 test 文件唯一性 | ✅ |

## §5 Inline Unit Tests（233 files）

> 与代码共生：每个 `src/*.ts` 多有对应 `*.test.ts`。命令：`pnpm test`；覆盖率 `pnpm test:coverage`。coverage 不强制 80%（D-series 共识）。

| 子目录 | 覆盖点 |
|--------|--------|
| `apps/api/src/*.test.ts` | API surface + owner-routes + channel-inbound/outbound + workspace-tools + memory + audit + governance |
| `apps/api/src/owner-routes/*.test.ts` | route handler unit |
| `apps/api/src/lib/*.test.ts` | lib helpers |
| `apps/api/src/routes/*.test.ts` | route-level tests |
| `packages/runtime/src/*.test.ts` | RunEngine + approval-runtime + working-set + delegate-runtime |
| `packages/domain/src/**/*.test.ts` | Domain 6 域 ADT + pure rules |
| `packages/adapters/src/**/*.test.ts` | model-router + slack + wechat + credentials + sandbox |
| `packages/ports/src/**/*.test.ts` | Port interfaces |
| `packages/persistence/src/**/*.test.ts` | Drizzle / in-memory runtime-store |
| `cli/src/*.test.ts` | CLI |

## §6 PRE-EXISTING / Known Skip（不修共识）

> D-series audit 经验：少数 test 持续 skip / flaky；ship claim 必须 fresh full verify，不能用 last batch green。

| Test | 状态 | 共识 |
|------|------|------|
| 部分 arch test PRE-EXISTING | 📅 偶尔 fail | D-series 共识不修 |
| recording-baseline fixture | 📅 部分 stale | 候选等 owner hand-trial |
| Knip dead-code report（per cycle） | 🟡 baseline | 每次 cycle 重测 |

## §7 CI / 方法学 gate

> `pnpm test:full` 跑全部 vitest 测试；CI 见 `.github/workflows/ci.yml`（butler-v5 单 job）。

| Gate | 命令 | 锚定 |
|------|------|------|
| **Format** | `pnpm format:check` | prettier |
| **Lint** | `pnpm lint` | eslint `--max-warnings 0` |
| **Typecheck** | `bash scripts/typecheck-gate.sh` | 7 个 workspace 包 |
| **Unit / contract** | `pnpm test` | 默认全量 vitest |
| **Acceptance** | `pnpm vitest run tests/acceptance --pool=forks` | 验收 harness |
| **Methodology 19·19** | `pnpm test:methodology` | `acceptance/methodology.test.ts` |
| **Loopback smoke** | `bash scripts/cutover/ci-smoke-regression.sh` | 无 iLink 回归 |
| **Knip deadcode** | `pnpm deadcode:knip` | 每 cycle baseline |

## §8 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 功能清单 | [`FEATURES.md`](FEATURES.md) |
| API endpoint | [`API_ENDPOINTS.md`](API_ENDPOINTS.md) |
| env vars | [`ENV.md`](ENV.md) |
| 目标架构（§20 invariants 锚定源） | [`../DESIGN.md`](../DESIGN.md) |
| 当前实现与 L4 验收 | [`architecture/wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html) |
| 工程治理 / gate | [`GOVERNANCE.md`](GOVERNANCE.md) |
| Agent 入口（含跑测约定） | [`../AGENTS.md`](../AGENTS.md) |

---

**End of TESTS.md** | 2026-11-18 v4 退役收敛 | **314 test files / 8 categories**（46 arch + 7 acceptance + 233 inline unit + 28 misc）
