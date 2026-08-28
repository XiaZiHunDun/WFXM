# Butler v5 Port Catalog

DESIGN §7 端口契约的当前**实际**消费/实现映射。
本文件与 `packages/ports/src/index.ts` 顶部 deprecation 注释保持同步。

---

## 1. 物化 Core 端口（DESIGN §7 实施）

| Port | File | Consumer(s) | Producer(s) | Inject 位置 |
| --- | --- | --- | --- | --- |
| **Clock** | `packages/ports/src/core/clock.ts` | `packages/runtime/src/run-engine.ts` (`systemClock`, `ClockPort`) | `apps/api/src/bootstrap-wiring.ts` (`systemClock`); tests (`fixedClock`) | RunEngine 构造注入 |
| **Credential Provider** | `packages/ports/src/core/credential-provider.ts` | `apps/api/src/workspace-tools.ts`, `packages/adapters/src/credentials/host-credentials.ts` | `packages/adapters/src/credentials/host-credentials.ts` (`createHostCredentialProvider`, `injectRunCommandCredentials`) | wiring + run_command 执行前 |
| **Event Store** | `packages/ports/src/core/event-store.ts` | `packages/runtime/src/agent-kernel.ts`, `packages/runtime/src/delegate-runtime.ts`, `packages/persistence/src/event-bridge.ts` | `packages/persistence/src/event-bridge.ts` | wiring |

---

## 2. R2 Effect Tag 端口（`packages/ports/src/index.ts` — @deprecated 2026-08-28）

仍由 `packages/adapters/src/postgres/*` 引用；**待 postgres 适配器迁移到 `/core/*` 后归档**。
本表是迁移看板，并非"已实施"清单。

| Tag | 生产 consumer | 状态 |
| --- | --- | --- |
| `OutboxService` | `packages/adapters/src/postgres/postgres-outbox.ts` | 待迁移 |
| `EventStoreService` | `packages/adapters/src/postgres/postgres-event-store.ts` | 与 `/core/event-store.ts` 已并存；postgres 适配器需切到窄接口后归档 |
| `SnapshotService` | `packages/adapters/src/postgres/postgres-snapshot.ts` | 待迁移 |
| `ProjectionService` | `packages/adapters/src/postgres/postgres-projection.ts` | 待迁移 |
| `Config` | `packages/config/src/index.ts` | 待迁（注意：与 `BUTLER_V5_*` env config 不同；本端口是 R2 时代 concept） |
| `LLMService` / `ToolExecutor` / `LoopInterrupt` / `GuardService` / `WeChatGateway` / `MCPDiscovery` / `ProjectService` / `MemoryService` / `WorkflowService` | **当前生产 delivery shell 不引用** (async/await + capability-boundary 已替代) | 待清理 / 归档 |

> 注：`MemoryService.dream` 对应 DESIGN §12 明文"当前不建设"的 Dream 两阶段巩固；
> `WorkflowService.start/send/merge` 对应 DESIGN §2 明文"不为未来规模预建通用 Workflow DAG"；
> `GuardService` 10 项含 `[G-9]`/`[G-10]` 是 AGENTS/butler-v5 §10 开发守卫，**不应进入生产 runtime**（production-architecture §0 / AGENTS §0 已分）。

---

## 3. 待物化（按真实需求触发，DESIGN §7 + P5）

- **Repository Port** — 当前 `runtime-store.ts` 函数签名耦合；待第二持久化实现或独立 mock 需求出现。
- **Model Port** — 当前 `model-router.ts` 调具体 adapter；待多 Provider 协议/记账统一需求出现。
- **Channel Port** — 当前 wechat/slack/telegram 各驱动；待第二 Channel 真接生产。
- **Capability 契约** — 已在 `capability-boundary.ts` 承载，"实现即接口"原则不重复建设。

---

## 4. 维护规则

- 新增/迁移 Port：同步本表 + DESIGN §7.1 + `.blackboard/state.md` 顶部 `_last_synced`。
- 移除端口：先标 `@deprecated` 一 release，再删 + 移归档。
- 严禁为"架构完整"造休眠接口（DESIGN §7）。
- 任何对 `index.ts` 的破坏性变更须先 `grep -RIn '@butler/ports' butler-v5/{packages,apps,cli}` 拿到 0 命中，方可执行。
