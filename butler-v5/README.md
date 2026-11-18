# Butler v5 — 微信接入的编码管家

> TypeScript pnpm monorepo。目标架构：[`DESIGN.md`](DESIGN.md) · 行为契约：[`AGENTS.md`](AGENTS.md) · 当前实现与第一阶段验收：[`../docs/architecture/wfxm-agent-runtime.html`](../docs/architecture/wfxm-agent-runtime.html)

## 当前状态

第一阶段（主要流程打通）已达标：微信入站 → 管家层 → 任务层主链路可用，无 5xx、无明显消息丢失；
L4 主流程 5/5、可靠性用例 5/5、评估场景 22/22 通过。第二阶段待办见架构文档「第一阶段达标判定」。

## 快速开始

```bash
pnpm install
pnpm test          # 全部单测 / 契约测试
pnpm typecheck     # 各包 tsc --noEmit
pnpm lint          # eslint（--max-warnings 0）
pnpm demo          # zero-LLM CLI REPL（脚本化 fixture LLM + 内存 PGlite）
```

真实模型启动与自托管：见 [`../docs/deployment/SELF-HOSTING.md`](../docs/deployment/SELF-HOSTING.md)；
本机生产部署为 systemd user 服务 `butler-v5-gateway.service`。

## 目录

```
butler-v5/
├── apps/api/            # HTTP 网关：入站路由、iLink 轮询、MCP、子代理 worker
├── cli/                 # 运维 CLI（sandbox 预检、诊断等）
├── packages/
│   ├── domain/          # 纯领域：治理决策、运行时契约、网络白名单
│   ├── ports/           # 端口（接口）定义
│   ├── adapters/        # 外部适配：沙箱(bubblewrap)、微信、LLM、存储实现
│   ├── runtime/         # 管家循环、任务执行、消息出口规范化
│   └── persistence/     # 运行时存储、事件桥、迁移
├── vendor/pi-agent/     # vendored pi agent core（agent loop / 状态 / 工具钩子）
├── scripts/             # 验收与冒烟脚本（含 scripts/l4-smoke.ts）
└── tests/               # 评估场景（tests/eval）与架构约束测试
```

## 分层验证

| 层 | 范围 | 命令 |
| --- | --- | --- |
| L1 | 单元 / 契约 | `pnpm test` |
| L2 | 消息出口规范化 | `vitest run packages/runtime/src/butler/presentation.test.ts` |
| L3 | 评估场景（gate） | `vitest run tests/eval` |
| L4 | 渠道前验收窗口（真实路由 + 真实 runtime） | `npx tsx scripts/l4-smoke.ts` |
| L4 可靠性 | 重投 / 并发 / 连续投递 / 无待审批 | `npx tsx scripts/l4-smoke.ts --suite reliability` |

L4 脚本要求网关已启动，并从 `~/.config/butler-v5/env` 读取 `BUTLER_V5_INBOUND_SHARED_SECRET`。

## 配置与运维

- 环境变量总表：[`../docs/ENV.md`](../docs/ENV.md)；配置面：[`../docs/config/config-surfaces.md`](../docs/config/config-surfaces.md)
- 生产加固：[`../docs/deployment/production-hardening.md`](../docs/deployment/production-hardening.md)
- 诊断入口：[`../docs/ops/diagnostic-entrypoints.md`](../docs/ops/diagnostic-entrypoints.md)

## 技术栈

TypeScript（strict）· Hono · Drizzle ORM + PostgreSQL（测试用 PGlite）· Vitest · pnpm · bubblewrap 沙箱
