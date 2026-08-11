# Butler v5 Contributing Guide

## 快速开始

```bash
# 环境要求
node -v   # >= 20
pnpm -v   # >= 9

# 安装依赖
pnpm install

# 运行全部测试
pnpm test

# 类型检查
pnpm typecheck
```

## 开发流程

### 1. 分支策略

- `main` — 保护分支，通过 CI 后合并
- `feat/*` — 新功能
- `fix/*` — Bug 修复
- `refactor/*` — 重构

### 2. 提交前检查

```bash
# 类型检查（8 包，0 错误）
pnpm typecheck

# 运行测试
pnpm test

# 死代码检测
pnpm deadcode

# 门禁检查
bash scripts/typecheck-gate.sh

# 按层级运行测试
bash scripts/run-test-layer.sh domain
bash scripts/run-test-layer.sh guard
```

### 3. 提交规范

```
type(scope): description

feat(domain): 新增 xxx 纯函数
fix(infra): 修复 xxx Layer 注入问题
refactor(ports): 重构 xxx Tag 接口
test(contracts): 新增 xxx 契约测试
docs(readme): 更新 xxx 文档
```

### 4. 受保护文件修改

以下文件需要人工修改并添加 `[MANUAL-OVERRIDE]` 标记：

| 文件                              | 原因            |
| --------------------------------- | --------------- |
| `packages/domain/src/errors.ts`   | 全局错误 ADT    |
| `packages/ports/src/index.ts`     | Effect Tag 接口 |
| `.cursorrules`                    | AI 守卫自身     |
| `AGENTS.md`                       | 行为契约        |
| `.butler/scope-boundaries.json`   | 安全边界        |
| `.butler/load-bearing-marks.json` | 承重代码        |

## 代码规范

### 类型定义

- 所有 union 类型用 `_tag` 区分
- 所有字段 `readonly`
- 禁止 `optional + null`，用可辨识 union

### 错误处理

- 禁止 `throw`，用 `Effect.fail`
- 所有可恢复错误走 `LoopError` ADT

### 导入规范

- 使用 `import type` 导入类型
- 禁止 `import *` 模式
- 禁止跨层反向导入

### 测试规范

- 文件名：`*.test.ts`
- 领域层：纯函数单元测试，零 mock
- 应用层：Mock Layer 注入
- 基础设施层：真实 Layer 集成测试
- 守卫测试：`tests/guard/`
- 契约测试：`tests/contracts/`

## 分层依赖

```
apps/* → application/, ports/, config/
application/ → ports/, domain/
infrastructure/ → ports/, domain/, config/
ports/ → domain/（仅类型）
domain/ → 零依赖
config/ → domain/（仅类型）
```

## 七级决策阶梯

在实现任何功能前，依次检查：

1. YAGNI — 这个需求真的需要实现吗？
2. 代码库复用 — 是否已有类似实现？
3. 标准库 — TypeScript/Node.js 标准库是否已提供？
4. 原生平台 — Effect-TS 是否已内置此能力？
5. 已安装依赖 — 已安装的依赖是否能解决？
6. 一行代码 — 能否用一行代码解决？
7. 最小实现 — 最后才写最小可用代码

## 7 条 GUARD

| #   | 机制           | 触发条件                                |
| --- | -------------- | --------------------------------------- |
| G-1 | 证据门控       | 每次写操作必须留存 IntentReceipt        |
| G-2 | 承重防护       | 修改 load-bearing 标记文件需 Owner 签名 |
| G-3 | Owner 离线策略 | 离线时 write/execute 拒绝               |
| G-4 | 签名验证       | 承重代码修改需 Owner HMAC 签名          |
| G-5 | 多文件链路     | 修改主文件时检查关联文件                |
| G-6 | 角色分离       | Author ≠ Reviewer                       |
| G-7 | 3 层自愈       | Retry → Fallback → OwnerNotify          |

## 工程约束

| 约束        | 阈值                  | 行为 |
| ----------- | --------------------- | ---- |
| 单文件行数  | >800                  | 警告 |
| 单文件行数  | >1200                 | 阻止 |
| 跨层 import | domain→infrastructure | 阻止 |
| 危险模式    | `import *`            | 阻止 |
| 全局副作用  | 模块级 `new Map()`    | 警告 |
