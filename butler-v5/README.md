# Butler v5 — 函数式架构微信编码管家

> TypeScript + Effect-TS + CQRS + Event Sourcing  
> 架构设计：[`DESIGN.md`](DESIGN.md) | 行为契约：[`AGENTS.md`](AGENTS.md) | 贡献指南：[`CONTRIBUTING.md`](CONTRIBUTING.md)

## 快速开始

```bash
pnpm install
pnpm test          # 运行全部测试（3062+ tests）
pnpm typecheck     # 8 包类型检查
pnpm lint          # 代码规范检查
```

## 项目结构

```
butler-v5/
├── apps/
│   ├── api/                  # HTTP API 服务（管理端点 + Webhook）
│   └── wechat-gateway/       # 微信入站/出站网关
├── packages/
│   ├── domain/               # 领域层：6 域 ADT + 纯函数
│   ├── ports/                # 端口层：Effect Tags（服务契约）
│   ├── application/          # 应用层：用例编排
│   ├── infrastructure/       # 基础设施层：实现 + 适配器
│   ├── config/               # 配置层：Schema + 环境变量
│   └── shared/               # 共享工具
├── docker-compose.yml        # 本地开发 PostgreSQL
├── vitest.config.ts          # 测试配置
└── turbo.json                # Turborepo 构建编排
```

## 架构概览

```
┌─────────────────────────────────────────────────┐
│  Apps（wechat-gateway / api）                    │
├─────────────────────────────────────────────────┤
│  Application（用例：runLoop / delegateTask /    │
│               runWorkflow / dream）              │
├───────────────┬─────────────────────────────────┤
│  Domain（纯函数）│  Ports（Effect Tags）           │
│  6 域 ADT     │  LLM / Guard / EventStore ...   │
├───────────────┴─────────────────────────────────┤
│  Infrastructure（Drizzle / LLM / WeChat / MCP） │
└─────────────────────────────────────────────────┘
```

## 领域层（6 域）

| 域           | 文件                       | 说明                    |
| ------------ | -------------------------- | ----------------------- |
| conversation | `domain/src/conversation/` | 对话状态机 + 上下文管线 |
| tools        | `domain/src/tools/`        | 工具定义 + 调用/结果    |
| memory       | `domain/src/memory/`       | 记忆记录 + Dream 两阶段 |
| workflows    | `domain/src/workflows/`    | Channel 多分支 + 状态机 |
| projects     | `domain/src/projects/`     | 项目 + Spec 管理        |
| permissions  | `domain/src/permissions/`  | 权限决策 + 承重代码     |
| guards       | `domain/src/guards/`       | 10 条 GUARD 防错        |
| errors       | `domain/src/errors.ts`     | 全局错误 ADT            |

## 10 条 GUARD 机制

| 编号 | 机制                   | 状态 |
| ---- | ---------------------- | ---- |
| G-1  | IntentReceipt 证据门控 | ✅   |
| G-2  | 承重代码保护           | ✅   |
| G-3  | Owner 离线策略         | ✅   |
| G-4  | HUMAN 签名验证         | ✅   |
| G-5  | 多文件链路校验         | ✅   |
| G-6  | 2 级验证选择           | ✅   |
| G-7  | 角色分离               | ✅   |
| G-8  | 3 层自愈               | ✅   |
| G-9  | 反模式归档             | ✅   |
| G-10 | 混沌演练               | ✅   |

## 测试

```bash
pnpm test              # 全部测试
pnpm test:watch        # 监听模式
pnpm test:coverage     # 覆盖率报告
pnpm typecheck         # 8 包类型检查
pnpm lint              # 代码规范检查

# 按层级运行
bash scripts/run-test-layer.sh domain    # 领域层
bash scripts/run-test-layer.sh app       # 应用层
bash scripts/run-test-layer.sh infra     # 基础设施层
bash scripts/run-test-layer.sh guard     # 守卫测试
bash scripts/run-test-layer.sh all       # 全部
```

## 环境变量

| 变量                                | 默认值                                                | 说明               |
| ----------------------------------- | ----------------------------------------------------- | ------------------ |
| `LOOP_MAX_ITERATIONS`               | 50                                                    | 单次循环最大迭代   |
| `LOOP_TIMEOUT_MS`                   | 600000                                                | 循环超时（ms）     |
| `GUARDS_OWNER_OFFLINE_THRESHOLD_MS` | 300000                                                | Owner 离线阈值     |
| `GUARDS_CHAOS_ENABLED`              | false                                                 | 混沌演练开关       |
| `LLM_PRIMARY`                       | anthropic                                             | 主 LLM provider    |
| `LLM_FALLBACK`                      | openai                                                | 备选 LLM provider  |
| `DATABASE_URL`                      | postgres://butler:butler_dev@localhost:5432/butler_v5 | 数据库连接         |
| `WECHAT_TOKEN`                      | butler-dev-token                                      | 微信签名验证 token |

## 技术栈

- **TypeScript 5.4+** strict mode
- **Effect-TS 3.4+** 函数式效果系统
- **Drizzle ORM** 数据库访问
- **PostgreSQL 16** 持久化
- **Vitest** 测试框架
- **pnpm + Turborepo** monorepo 管理
