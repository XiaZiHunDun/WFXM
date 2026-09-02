# S3 — ports + adapters 会话（端口/适配层）

**职责**：负责 `packages/ports/src/core/**`（除 `index.ts` 归 S1）与 `packages/adapters/**`——端口声明、provider 实现、adapter。热点 = Channel Port、provider 接入、依赖方向的边界纪律。

## 独占路径

- `packages/ports/src/core/**`（各 `.ts` 与 `.test.ts`，**不含** `packages/ports/src/index.ts`）
- `packages/adapters/**`

## 边界（不可动）

- `packages/ports/src/index.ts`（thin barrel）归 **S1**：新增端口文件后，**提 PR 让 S1 加 `export *` + `package.json exports`** + 更新 `port-catalog.md` / `DESIGN.md §7.1`。
- `packages/ports/port-catalog.md`、`DESIGN.md` 归 S1，不在本会话手写。
- **依赖方向（架构硬约束，arch guard 锁）**：
  - `ports` 只 import `@butler/domain`（先例：`event-store.ts` import domain ActorRef）。**禁止** import `persistence / runtime / adapters / apps`。
  - `adapters` 可 import `domain + ports`，**禁止** import `runtime / apps`。
  - 端口保持 interface-only：0 class / 0 fetch / 0 db / 0 IO（D31 lock）。

## 依赖/上游

- 依赖 S2（domain 契约）。若端口需要新契约 → 给 S2 下单加 domain 类型。
- 被 S5/S6 消费，签名稳定为先。

## 常规先手

- 新端口按"真实可替换接缝"触发（DESIGN §7：不预造休眠接口）。举例：Channel Port（等 Slack/Telegram 真接生产）；Repository Port 已由 D46 物化。
- adapter 改 provider 时同步单测。

## 最小门禁（提交前）

```bash
cd butler-v5/packages/ports && pnpm exec tsc --noEmit
cd butler-v5/packages/adapters && pnpm exec tsc --noEmit
cd butler-v5 && CI= pnpm exec vitest run packages/ports packages/adapters tests/architecture/section7 tests/architecture/section7-1-repository -q
pnpm exec eslint packages/ports packages/adapters --ext .ts --max-warnings 0
```

## 当前相关待办

- **Channel Port 已退役（2026-09-02）**：owner 确认目前只用微信，不接真 Slack/Telegram → 不作硬物化（DESIGN §7 禁造休眠接口）。**本会话暂无独占主任务**；可承接的整理类工作：`packages/ports/src/core/**` 与 `packages/adapters/**` 内部代码规范/技术债、测试补强、port-catalog 与 DESIGN §7 一致性（全局文档改动仍归 S1，你提 PR 由 S1 收）。
- 配合 S1：新增端口后提交 barrel 接入 PR（当前无新增）。
- MemoryService（§12）若后续触发物化，本会话与 S5/S6 协同（S1 领衔）。