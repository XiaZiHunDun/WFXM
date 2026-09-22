# Butler v5 — Test Coverage Inventory

> **生成日期**: 2026-09-22 | **状态**: post-D79 (127 ship 累計) | **读者**: Owner / Contributor / 审稿人
> **关系**:
> - 功能视角 → [`FEATURES.md`](FEATURES.md)
> - HTTP/WS API → [`API_ENDPOINTS.md`](API_ENDPOINTS.md)
> - env vars → [`ENV.md`](ENV.md)
> - 目标架构（§3-§20 invariants 锁源）→ [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md)
> - 自托管指南（冒烟验收）→ [`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md)
> - production hardening（§20 invariant 锚定）→ [`deployment/production-hardening.md`](deployment/production-hardening.md)
> - Agent 入口 → [`../AGENTS.md`](../AGENTS.md)

---

## 图例

- ✅ **已 ship**（CI 跑绿 + 守门齐全）
- 🟡 **已 ship 子集**（核心 pass，外延未完）
- 📅 **延后 / PRE-EXISTING**（已知 carry；D-series 共识不修）
- ❌ **明确 skip**（decline；保留）

## §0 总览 / 统计

| 类别 | test 文件数 | 跑绿状态 |
|------|------------|----------|
| Architecture（§3-§20 invariants） | **47** | 19·19（methodology 锚定） |
| Acceptance（harness + realistic + regression + subagent + audit-state + fault-tolerance + commands-approval + methodology） | **8** | 105 scenario（`/audit=1`） |
| E2E（r7-wiring + r8-real-persistence） | **2** | ✅ |
| Contracts（port stability） | **1** | ✅ |
| Eval（harness + scenarios + mock-llm） | **3** helper | ✅ |
| Guard（meta-audit + no-layer-violation） | **2** | ✅ |
| _meta（typed-rules + unique-list） | **2** | ✅ |
| **Inline unit**（apps/api/src + packages/*/src + cli/src） | **238** | ✅ |
| **Total test files** | **321** | 各类 gate 见 §1-§8 |

> **数法说明**：用 `find . -name "*.test.ts"` 统计；不含 `_meta/_meta` 自身。

## §1 Architecture Tests（47 files / §3-§20 invariants）

> DESIGN §20 不变量 → 每个 arch test 锁 1 条；D-series 26 cycles 累计加锁。`section*-*.test.ts` 命名约定。

### §1.1 依赖方向 & Core 不变量（§3）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `dependency-direction.test.ts` | 依赖方向向内核 | D17+ | ✅ |
| `section3-dependency-rules.test.ts` | §3 #1-#6 全 6 cases（D33 case #1-#6） | D33 | ✅ |
| `domain-zero-io.test.ts` | Domain 零 I/O（§5） | D17 | ✅ |
| `section5-domain-pure.test.ts` | Domain pure 函数 8 cases | D25 | ✅ |
| `single-llm-tool-loop.test.ts` | 单 LLM + tool 调用循环 | D40 | ✅ |
| `working-set-budget-no-delete.test.ts` | working-set 超预算只压缩不删（§6.1 / §20 #14） | D14/D40 | ✅ |
| `three-memory-separation.test.ts` | 3 记忆层 cross-import = 0（§12 / §20 #9） | D9 | ✅ |

### §1.2 Application & Orchestrator（§6）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `section6-application-orchestrator.test.ts` | RunEngine 7 职责 + 5-tag ADT（§6 / D34） | D34 | ✅ |
| `r2-end-to-end.test.ts` | RunEngine E2E（plan → exec → finish） | R2 | ✅ |
| `r3-end-to-end.test.ts` | RunEngine + policy gate + audit | R3 | ✅ |
| `r4-end-to-end.test.ts` | RunEngine + approval flow | R4 | ✅ |
| `r5-end-to-end.test.ts` | RunEngine + waiting_external | R5 | ✅ |
| `r6-end-to-end.test.ts` | RunEngine + outbox + persistence | R6 | ✅ |
| `side-effect-throat.test.ts` | 所有副作用必经 canonical runButlerLoop（§3 #5） | D26A | ✅ |

### §1.3 Ports（§7）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `section7-ports-main.test.ts` | thin barrel + interface-only + 依赖向内 | D31 | ✅ |
| `section7-1-port-snapshot.test.ts` | 7 v5 物化 Core Port 完整性 | D11 | ✅ |
| `section7-1-model-port.test.ts` | Model Port 物化（D44 P5） | D44 | ✅ |
| `section7-1-repository.test.ts` | Repository Port 物化（D46 第二实现触发） | D46 | ✅ |
| `mcp-contract.test.ts` | MCP thin client 契约 | D29 | ✅ |
| `mcp-spawn-arch.test.ts` | MCP spawn arch 边界 | D40 | ✅ |
| `unwired-packages-archived.test.ts` | `_archive` 隔离（§17.3） | D32 | ✅ |

### §1.4 Driving/Driven Adapters（§8-§9）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `section8-9-adapters-boundary.test.ts` | Trigger + Capability 边界 | D29 | ✅ |
| `apps-layer-boundaries.test.ts` | apps 不允许 `runTool*` 旁路（§1.1） | D33 | ✅ |
| `capability-no-auto-grant.test.ts` | Capability 不自动 grant | D31 | ✅ |
| `workspace-sandbox-arch.test.ts` | workspace + sandbox arch | D40 | ✅ |

### §1.5 Governance（§10）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `section10-governance-arch-guard.test.ts` | §10 9 cases | D13/D27 | ✅ |
| `section10-4-6-13-deep-audit.test.ts` | §10.4-6 + §13 10 cases deep audit | D34 | ✅ |
| `child-run-permission-not-wider.test.ts` | Child Run 不宽于父（§4.2 / §20 #5） | D-series | ✅ |
| `child-run-cancel-cascade.test.ts` | 父 cancel 级联 | D-series | ✅ |

### §1.6 Persistence（§11）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `section11-1-2-3-current-state-immutable.test.ts` | 7 cases（Current State + Append-only + Outbox） | D28 | ✅ |
| `section11-deferred-triggered.test.ts` | §11.4 trigger-conditioned | D22 | ✅ |
| `outbox-post-transactional.test.ts` | Outbox 事务原子性（§20 #8） | D7 | ✅ |
| `audit-event-tx-atomicity.test.ts` | `audit_events` 事务原子性（§11.2） | D-series | ✅ |

### §1.7 Knowledge & Memory（§12）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `section12-knowledge-memory.test.ts` | 3 层独立 + 6 cases（§12 D30） | D30 | ✅ |

### §1.8 Observability（§14）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `section14-observability-fields.test.ts` | 14 fields 捕获（D21+D23） | D21-D23 | ✅ |
| `section14-token-cost.test.ts` | 9 cases token 路径 | D23 | ✅ |
| `section14-costusd.test.ts` | 7 cases costUsd 路径 | D24 | ✅ |

### §1.9 Engineering / Process（§15-§17）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `section15-effect-discipline.test.ts` | Effect-TS 工程范式 | D-series | ✅ |
| `section16-process-boundary.test.ts` | 单进程模块化单体边界 | D-series | ✅ |
| `section17-1-2-monorepo-management.test.ts` | workspace 3 glob + 5 active packages（§17.1+§17.2） | D32 | ✅ |
| `section17-3-orphan-package.test.ts` | `_archive` 隔离（§17.3） | D18/D19 | ✅ |
| `package-membership.test.ts` | archived R2 shim isolation（C11 / invariant 16） | D-series | ✅ |

### §1.10 Trigger & Invariants（§18-§20）

| File | 锁定 invariant | Cycle | 状态 |
|------|----------------|-------|------|
| `section18-trigger.test.ts` | §18 deferral trigger-条件未达（实时检测） | D-series | ✅ |
| `section20-invariants-batch-a.test.ts` | §20 invariant 批次 A | D-series | ✅ |
| `section20-invariants-batch-b.test.ts` | §20 invariant 批次 B | D-series | ✅ |
| `section0-1-2-19-sweep.test.ts` | §0 + §1 + §2 + §19 sweep（governance / 工程边界） | D-series | ✅ |
| `p3-seam-guard.test.ts` | P3 seam 守护 | D-series | ✅ |

## §2 Acceptance Tests（8 files / 58 scenarios）

> `pnpm test:acceptance` / `pnpm test:full`；harness 启动生产 wiring + 内存 PGlite + 脚本化 fixture LLM。

| File | 类别 | 场景数 | 状态 |
|------|------|--------|------|
| `acceptance/scenarios/realistic.test.ts` | **58 真实场景产品层行为**（A1-A11 + B1-B10 + C1-C10 + D1-D5 + E1-E3） | 235+ (N=3 verify) | ✅ (D52 + D79 T2) |
| `acceptance/product-regressions.test.ts` | **微信产品层回归**：/undo + spam guard + LLM tracer + inline-approval + run_command argv + P2 batch | 13 | ✅ |
| `acceptance/commands-approval.test.ts` | **命令 + approval 矩阵**：/撤销 /重试 /确认 / 拒絕 | ~10 | ✅ |
| `acceptance/subagent-multiturn.test.ts` | **subagent 多轮** D-series 4th cycle carry | ~6 | ✅ |
| `acceptance/fault-tolerance.test.ts` | **fault tolerance**：3 层自愈（G-8） | ~5 | ✅ |
| `acceptance/audit-state.test.ts` | **audit emit actor**（currentOwnerActor） | ~4 | ✅ |
| `acceptance/methodology.test.ts` | **methodology 19·19**（含 M15 docker-deploy） | 19 | ✅ (D77 T7) |
| `acceptance/scenarios/_analyze.md` | **58 场景 baseline 分析**（生成日期 2026-09-22） | — | ✅ (regen post-batch) |

### §2.1 Acceptance harness 支持

| File | 作用 | 状态 |
|------|------|------|
| `acceptance/harness.ts` | `makeAcceptanceApp()` — 生产 wiring + 内存 PGlite + 脚本化 LLM | ✅ |
| `acceptance/multi-round.ts` | N-round verify helper | ✅ |
| `acceptance/methodology-index.ts` | methodology 索引 | ✅ |
| `acceptance/scenarios/_fixtures.ts` | scenario fixtures（trigram dedup 等） | ✅ |
| `acceptance/scenarios/recordings/{A,B,C,D,E}*.json` | per-scenario expected fixtures | ✅ |
| `acceptance/scenarios/recordings-archive/v1-v7/` | 历史 baseline（v7-current 是当前 SSOT） | ✅ |

## §3 E2E Tests（2 files）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `e2e/r7-wiring.e2e.test.ts` | apps/api wiring + Channel Port 注入 + iLink fallback | ✅ |
| `e2e/r8-real-persistence.e2e.test.ts` | 真 Postgres 路径（pglite + Drizzle） | ✅ |

## §4 Contracts Tests（1 file）

| File | 锁定 invariant | 状态 |
|------|----------------|------|
| `contracts/test_port_stability.test.ts` | Port 契约稳定（`EXPECTED_EXPORTS` / `EXPECTED_PORT_FILES`） | ✅ |

## §5 Eval Tests（3 helper files）

> D44 P5 Model Port + LLM eval 工具集。

| File | 作用 | 状态 |
|------|------|------|
| `eval/harness.ts` | eval harness 入口 | ✅ |
| `eval/metrics.ts` | eval 指标 | ✅ |
| `eval/mock-llm-scripted.ts` | eval 模式脚本化 LLM | ✅ |
| `eval/scenarios/` | eval scenarios | ✅ |

## §6 Guard Tests（2 files）

> 工程治理 gate。

| File | 作用 | 状态 |
|------|------|------|
| `guard/meta-audit.test.ts` | meta-audit gate（cross-check methodology / D-series） | ✅ |
| `guard/no-layer-violation.test.ts` | 无 layer 违规（§3 依赖方向硬规则） | ✅ |

## §7 _meta Tests（2 files）

> 守护 test 文件本身正确性。

| File | 作用 | 状态 |
|------|------|------|
| `_meta/architecture-typed-rules.test.ts` | architecture test 类型化规则 | ✅ |
| `_meta/list-unique-test-files.test.ts` | test 文件 ID 唯一性 | ✅ |

## §8 Inline Unit Tests（238 files）

> 与代码共生：每个 src/*.ts 多有对应 *.test.ts。CI 跑绿；coverage 不强制 80%（D-series 共识）。

| 子目录 | test 文件数 | 覆盖点 |
|--------|-------------|---------|
| `apps/api/src/*.test.ts` | ~80 | API surface + owner-routes + channel-inbound/outbound + workspace-tools + memory + audit + governance |
| `apps/api/src/owner-routes/*.test.ts` | ~3 | route handler unit |
| `apps/api/src/lib/*.test.ts` | ~5 | lib helpers |
| `apps/api/src/routes/*.test.ts` | ~5 | route-level tests |
| `packages/runtime/src/*.test.ts` | ~25 | RunEngine + approval-runtime + working-set + delegate-runtime |
| `packages/domain/src/**/*.test.ts` | ~80 | Domain 6 域 ADT + pure rules |
| `packages/adapters/src/**/*.test.ts` | ~25 | model-router + slack + wechat + credentials + sandbox |
| `packages/ports/src/**/*.test.ts` | ~5 | Port interfaces |
| `packages/persistence/src/**/*.test.ts` | ~10 | Drizzle / in-memory runtime-store |
| `packages/config/src/*.test.ts` | ~3 | config loader |
| `packages/shared/src/*.test.ts` | ~2 | shared utilities |
| `cli/src/*.test.ts` | ~2 | CLI |
| **Inline unit total** | **~238** | per §8 + §13.1 + G-2 (承重代码保护) |

## §9 PRE-EXISTING / Known Skip（不修共识）

> D-series audit 经验：少数 test 持续 skip / flaky；D50 lesson — ship claim 用 last batch green 不可信，必须 fresh full verify。

| Test | 状态 | 共识 |
|------|------|------|
| 部分 arch test PRE-EXISTING | 📅 偶尔 fail | D-series 共识不修 |
| recording-baseline fixture（v7-current） | 📅 部分 stale | v8 candidate A/B/C 3/3 revert，候选 D 等 owner hand-trial |
| Knip dead-code report（per cycle） | 🟡 baseline | 每次 cycle 重测 |

## §10 CI / 方法学 gate

> `pnpm test:full` 跑：lint + typecheck + methodology 19·19 + acceptance 105 + arch + unit。

| Gate | 命令 | 锚定 |
|------|------|------|
| **Lint** | `pnpm lint` | D-series 持续 0 |
| **Typecheck** | `pnpm typecheck` | D-series 持续 7·7（7 packages） |
| **Methodology 19·19** | `pnpm test:acceptance methodology` | `acceptance/methodology.test.ts` |
| **Acceptance scenarios** | `pnpm test:acceptance` | 105 pass（含 E1-E3 D79 T2） |
| **Architecture** | `pnpm test:architecture` | 47 files / D-series 累计 lock |
| **Unit** | `pnpm test:unit` | ~238 files inline |
| **Knip deadcode** | `pnpm knip` | 每 cycle baseline |

## §11 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 功能清单 | [`FEATURES.md`](FEATURES.md) |
| API endpoint | [`API_ENDPOINTS.md`](API_ENDPOINTS.md) |
| env vars | [`ENV.md`](ENV.md) |
| 目标架构（§20 invariants 锚定源） | [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) |
| D-series 累计 | [`ROADMAP.md`](ROADMAP.md) |
| Agent 入口（含跑测约定） | [`../AGENTS.md`](../AGENTS.md) |

---

**End of TESTS.md** | D80 cycle 26 inventory batch | **321 test files / 8 categories**（含 47 arch + 8 acceptance + 238 inline unit + 28 misc）