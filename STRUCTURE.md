# 仓库目录结构

> Butler v5（`butler-v5/`）是唯一活动实现：TypeScript + pnpm monorepo 的微信接入编码管家。
> 新会话先读 [`AGENTS.md`](AGENTS.md)；文档分层见 [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md)。
> `reference/` 为主公维护的外部对照标本区（gitignore），整理时不修改。

```text
WFXM/
├── butler-v5/                  # ★ v5 全部产品代码、配置与验收脚本
│   ├── apps/api/               #   HTTP/WS 网关、iLink 轮询、管家循环与工具 / 子代理 worker
│   ├── cli/                    #   运维 CLI：start、wechat-login、sandbox 预检与探测
│   ├── packages/
│   │   ├── domain/             #   纯领域类型与治理策略（零 I/O）
│   │   ├── ports/              #   Port 接口定义
│   │   ├── adapters/           #   LLM、微信、沙箱、存储等外部适配
│   │   ├── runtime/            #   管家循环、Run 引擎、消息出口规范化
│   │   └── persistence/        #   运行时存储、事件桥、数据库迁移
│   ├── vendor/pi-agent/        #   vendored agent core（loop / 状态 / 工具钩子）
│   ├── tests/                  #   架构、契约、验收、E2E、评估与 guard 测试
│   ├── scripts/                #   分层测试、L4 冒烟、demo 与 cutover 脚本
│   └── config/                 #   LLM 夹具、OpenAPI、MCP manifest、项目与调度配置
├── docs/                       # 文档：architecture、adr、deployment、plans、templates 与根层梳理文档
├── projects/                   # 试点项目工作区（LingWen1、DemoPilot 等）
├── scripts/ai_guard/           # git 守卫脚本；由 butler-v5 的 postinstall 安装 pre-commit / commit-msg hook
├── .github/workflows/          # CI（butler-v5 单 job）与发布工作流
└── reference/                  # 【不动】外部对照标本（gitignore）
```

## 常用命令

```bash
cd butler-v5
pnpm install                      # postinstall 同步 scripts/ai_guard 的 git hooks
pnpm typecheck
pnpm lint
pnpm test
npx tsx scripts/l4-smoke.ts       # L4 渠道前验收（需网关已启动）
```

## 文档入口

| 文档 | 说明 |
|------|------|
| [`README.md`](README.md) | 项目总览与快速开始 |
| [`AGENTS.md`](AGENTS.md) | Agent 必读索引与 v5 事实规则 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 安装、测试分层、AI Guard 与提交规范 |
| [`docs/README.md`](docs/README.md) | 文档索引（「我要…」快速链接） |
| [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) | 文档分层与维护规则 |
| [`butler-v5/DESIGN.md`](butler-v5/DESIGN.md) | v5 目标架构 |
| [`docs/architecture/wfxm-agent-runtime.html`](docs/architecture/wfxm-agent-runtime.html) | 当前实现全景与第一阶段验收 |
| [`docs/architecture/v5-production-architecture-2026-08.md`](docs/architecture/v5-production-architecture-2026-08.md) | 当前生产调用链与包边界 |
| [`docs/deployment/SELF-HOSTING.md`](docs/deployment/SELF-HOSTING.md) | 自托管部署指南 |
| [`docs/TESTS.md`](docs/TESTS.md) | 测试分层与命令 |
