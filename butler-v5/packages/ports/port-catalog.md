# Butler v5 Port Catalog

DESIGN §7 端口契约的当前**实际**消费/实现映射。
本文件与 `packages/ports/src/index.ts`（thin barrel）顶部注释保持同步。

最近更新：2026-08-31 D37/D38 收尾——§7.1 状态表与 §3 待物化段同步（Channel Port 行与 §7.1 🟡 一致）；6 v5 物化 Core Port 实证（C12）；r2-shim isolation（C11）。R2 Effect Tag 体系（14 个 Effect Tag）已于 2026-08-28 R12 收尾归档（commit `33af1722`，详见 §2 历史段）。

---

## 1. 物化 Core 端口（DESIGN §7 实施）

| Port | File | Consumer(s) | Producer(s) | Inject 位置 |
| --- | --- | --- | --- | --- |
| **Clock** | `packages/ports/src/core/clock.ts` | `packages/runtime/src/run-engine.ts` (`systemClock`, `ClockPort`) | `apps/api/src/bootstrap-wiring.ts` (`systemClock`); tests (`fixedClock`) | RunEngine 构造注入 |
| **Credential Provider** | `packages/ports/src/core/credential-provider.ts` | `apps/api/src/workspace-tools.ts`, `packages/adapters/src/credentials/host-credentials.ts` | `packages/adapters/src/credentials/host-credentials.ts` (`createHostCredentialProvider`, `injectRunCommandCredentials`) | wiring + run_command 执行前 |
| **Event Store** | `packages/ports/src/core/event-store.ts` | `packages/runtime/src/agent-kernel.ts`, `packages/runtime/src/delegate-runtime.ts`, `packages/persistence/src/event-bridge.ts` | `packages/persistence/src/event-bridge.ts` | wiring |
| **Outbox** | `packages/ports/src/core/outbox.ts` | R12 production runtime 直调 `@butler/persistence/outbox.js`；新 Port 为未来替换/隔离触发的接缝 | `memoryOutbox()` (本文件提供)；prod 实现待 R5.x 触发 | wiring |
| **Snapshot** | `packages/ports/src/core/snapshot.ts` | R12 production runtime 直调 `@butler/persistence/snapshot.js`；同上 | `memorySnapshot()` (本文件)；prod 实现待触发 | wiring |
| **Projection** | `packages/ports/src/core/projection.ts` | R12 production runtime 直调 `@butler/persistence/projections.js`；同上 | `memoryProjection()` (本文件)；prod 实现待触发 | wiring |

---

## 2. R2 Effect Tag 体系（**已归档 2026-08-28**）

R2 时代的 14 个 Effect Tag 接口（`LLMService` / `ToolExecutor` / `EventStoreService` / `OutboxService` / `SnapshotService` / `ProjectionService` / `LoopInterrupt` / `GuardService` / `WeChatGateway` / `MCPDiscovery` / `ProjectService` / `MemoryService` / `WorkflowService` / `Config`）已随 commit `33af1722` 整体归档：

- `packages/ports/src/index.ts` 改写为 thin barrel（`export * from "./core/*"`），全部 Tag 类移除
- 生产 runtime 不经这些 Tag 注入面（async/await + 直调 `@butler/persistence`）
- postgres 适配器 4 文件为 R2 adapter skeleton（实测零 caller），`git rm` 一并清理
- `Config` Tag 被 `loadConfig()` 纯函数取代（`packages/config/src/index.ts`）

完整 14 Tag 原文保留在 git history（commit `33af1722^`）。需参考可用：
`git show 33af1722^:butler-v5/packages/ports/src/index.ts`。

DESIGN 不变量 [G-4]：原 `GuardService` 10 项（含 `[G-9]` `[G-10]`）属开发仓库守卫，**不应进入生产 runtime**——归档历史已合于此原则（agentry §0 / butler-v5 §0 同分）。

---

## 3. 待物化（按真实需求触发，DESIGN §7 + P5）

- **Repository Port** — 当前 `runtime-store.ts` 函数签名耦合；待第二持久化实现或独立 mock 需求出现。
- **Model Port** — 当前 `model-router.ts` 调具体 adapter；待多 Provider 协议/记账统一需求出现。
- **Channel Port** — 🟡 接口已在 `packages/ports/src/core/channel.ts` 实装（DESIGN §7.1）；wechat adapter 上线（`packages/adapters/src/wechat/channel-port.ts` iLink impl，Composition Root 注入 `wiring.channels`）；slack adapter skeleton 就位（`packages/adapters/src/slack/`，5 文件 + `index.ts`，含 `slack-outbound*.ts` / `slack-protocol.ts` / `slack-media.ts`，**未实现 ChannelPort 接口**）等真接生产触发（DESIGN §18 条件准入）；telegram 未触发（无 adapter 目录）。Channel Port 真接生产触发后会升 ✅。
- **Capability 契约** — 已在 `capability-boundary.ts` 承载，"实现即接口"原则不重复建设。
- **MemoryService** — MVP 直调 `@butler/persistence/{durable-memory,document,project-knowledge}-store`，未物化 Core Port；与 Channel Port 类比，待 §7 audit 触发物化。Owner 路径走 `apps/api/src/{durable-memory-inject,project-knowledge-inject,wechat-memory-commands}.ts` + `owner-routes.ts`；Runtime 工具面 `recall_*` 直调 `@butler/persistence`。DESIGN §12 line 605 + §18 row 3（2026-09-01 D39 G3）实证。

---

## 4. 维护规则

- 新增/迁移 Port：同步本表 + DESIGN §7.1 + `.blackboard/state.md` 顶部 `_last_synced`。
- 移除端口：先标 `@deprecated` 一 release，再删 + 移归档。
- 严禁为"架构完整"造休眠接口（DESIGN §7）。
- 任何对 `index.ts` 的破坏性变更须先 `grep -RIn '@butler/ports' butler-v5/{packages,apps,cli}` 拿到 0 命中，方可执行。
