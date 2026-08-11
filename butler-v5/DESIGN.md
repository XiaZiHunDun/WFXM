# Butler v5 — 设计系统文档（DESIGN.md）

> 本文档是 Butler v5 的**规范驱动开发（SDD）权威参考**。
> 与 `AGENTS.md`（AI 行为契约）、`.cursorrules`（代码规则）构成三层约束体系。
>
> **反馈链路**：`DESIGN.md`（设计）→ `AGENTS.md`（行为）→ `.cursorrules`（规则）→ `hooks/`（执行）

---

## 一、架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│  apps/                                                            │
│  ├── wechat-gateway/  微信入站 + 出站                             │
│  └── api/             HTTP API（管理端点 + Webhook）              │
├──────────────────────────────────────────────────────────────────┤
│  packages/                                                         │
│  ├── domain/          纯函数 + ADT（零依赖）                      │
│  ├── ports/           Effect Tag 接口定义                         │
│  ├── application/     用例编排（Effect.gen）                      │
│  ├── infrastructure/  副作用实现（Layer DI）                      │
│  ├── config/          单 Schema 配置                              │
│  └── shared/          跨包通用工具                                │
└──────────────────────────────────────────────────────────────────┘
```

## 二、分层依赖规则

```
apps/* → application/, ports/, config/
application/ → ports/, domain/
infrastructure/ → ports/, domain/, config/
ports/ → domain/（仅类型）
domain/ → 零依赖
config/ → domain/（仅类型）
```

**禁止依赖**：

- `domain/` 不依赖任何包
- `ports/` 不依赖 `application/` 或 `infrastructure/`
- `infrastructure/` 不依赖 `application/`

## 三、核心范式：FC/IS（函数式核心 + 命令式外壳）

### 函数式核心（Functional Core）：`domain/`

- ADT 类型定义（`_tag` 区分，`readonly` 字段）
- 纯函数（zero I/O, zero side effects）
- 状态机 transition（输入 state + event → 输出 state）
- 零 mock 单元测试

### 命令式外壳（Imperative Shell）：`application/` + `infrastructure/`

- `application/`：Effect.gen 编排业务流程
- `infrastructure/`：Layer 实现副作用（DB, LLM, WeChat, MCP）
- Fiber 并发、Schedule 重试、Stream 事件流

### 一切皆可重放

- 事件流：`ConversationEvent → EventStoreService.append()`
- 状态投影：`projectConversation(events) → ConversationState`（确定性归约）
- 读模型：`loadConversation(events) → 当前状态`
- `DeltaChannel`：增量检查点，只加载新事件，避免全量重放

## 四、三层体验模型（AX / DX / UX）

| 层     | 全称                 | 受众        | 在 Butler v5 中的体现                                       |
| ------ | -------------------- | ----------- | ----------------------------------------------------------- |
| **AX** | Agent Experience     | AI 编码工具 | `AGENTS.md` + `.cursorrules` + `DESIGN.md` + `hooks/`       |
| **DX** | Developer Experience | 人类开发者  | `pnpm test` + `pnpm typecheck` + `pnpm gate` + 七级决策阶梯 |
| **UX** | User Experience      | 最终用户    | 微信消息交互 + HTTP API                                     |

**设计原则**：AX 服务于 AI 工具的正确性和安全性，DX 服务于人类开发效率，UX 服务于最终产品体验。三层各自独立，通过契约文件（`DESIGN.md` / `AGENTS.md`）桥接。

## 五、8 道防线

| #   | 防线                   | 实现                                         | 状态 |
| --- | ---------------------- | -------------------------------------------- | ---- |
| 1   | AI 配置契约            | `AGENTS.md` + `.cursorrules` + `DESIGN.md`   | ✅   |
| 2   | 类型系统约束           | Effect-TS + ADT `_tag` + `readonly`          | ✅   |
| 3   | 测试 + CI 门禁         | `typecheck-gate.sh` + `ci.yml` + `pnpm gate` | ✅   |
| 4   | 死代码检测             | `ts-prune` 检查未使用导出                    | ✅   |
| 5   | 架构不变量显式化       | Guard tests + Meta-audit tests               | ✅   |
| 6   | 供应链安全             | —（不在当前范围）                            | —    |
| 7   | 证据驱动 QA + 写审分离 | G-1（证据门控）+ G-6（角色分离）             | ✅   |
| 8   | Fail-fast + 可观测     | Effect 错误传播 + 结构化日志                 | ⚠️   |

## 六、7 条 GUARD 机制（精简版）

| #       | 机制           | 说明                                                     | 状态 |
| ------- | -------------- | -------------------------------------------------------- | ---- |
| **G-1** | 证据门控       | 每次写操作留存 `IntentReceipt`，NO EVIDENCE == NO COMMIT | ✅   |
| **G-2** | 承重防护       | 修改 load-bearing 标记文件需 Owner 签名                  | ✅   |
| **G-3** | Owner 离线策略 | 离线时 write/execute 拒绝，delegate 入队                 | ✅   |
| **G-4** | 签名验证       | 承重代码修改需 Owner HMAC 签名                           | ✅   |
| **G-5** | 多文件链路     | 修改主文件时检查关联文件是否同步                         | ✅   |
| **G-6** | 角色分离       | Author ≠ Reviewer                                        | ✅   |
| **G-7** | 3 层自愈       | Retry → Fallback → OwnerNotify                           | ✅   |

> 原 G-9（反模式归档）、G-10（混沌演练）降级为预留功能，不在 7 条核心 GUARD 中。

## 七、事件溯源 + CQRS

- 事件流：`ConversationEvent → EventStoreService.append()`
- 状态投影：`projectConversation(events) → ConversationState`
- 读模型：`loadConversation(events) → 当前状态`
- `DeltaChannel`：增量检查点，只加载新事件

## 八、测试策略

### 测试金字塔

| 层               | 测试类型        | Mock 策略        | 占比 |
| ---------------- | --------------- | ---------------- | ---- |
| domain/          | 纯函数单元测试  | 零 mock          | 最多 |
| application/     | Effect 编排测试 | Mock Layer 注入  | 中等 |
| infrastructure/  | 集成测试        | 真实 Layer       | 较少 |
| tests/guard/     | 守卫测试        | 架构约束静态分析 | 少量 |
| tests/contracts/ | 契约测试        | Port 接口稳定性  | 少量 |

### 快照测试（Snapshot Tests）

- 用于 `projectConversation()` 状态投影：给定事件序列，快照预期状态
- 用于 `ConfigSchema` 校验：默认配置快照，防止意外修改

### 测试文件命名

- 领域纯函数：`pure.test.ts`
- 基础设施 Layer：`*-service.test.ts` 或 `*-live.test.ts`
- 守卫测试：`tests/guard/*.test.ts`
- 契约测试：`tests/contracts/*.test.ts`

## 九、配置管理

- 单 Schema：`@effect/schema` 定义 `ConfigSchema`
- 三级加载：环境变量 → 默认值 → 类型校验
- 测试用 `makeTestConfig(overrides)` 覆盖

## 十、七级决策阶梯（防过度工程）

Agent 在编码前依次检查，在第一个满足的阶梯停下：

```
1. YAGNI        — 这个需求真的需要实现吗？
2. 代码库复用    — 是否已有类似实现？（先 grep 搜索）
3. 标准库       — TypeScript/Node.js 标准库是否已提供？
4. 原生平台     — Effect-TS 是否已内置此能力？
5. 已安装依赖   — 已安装的依赖是否能解决？
6. 一行代码     — 能否用一行代码解决？
7. 最小实现     — 最后才写最小可用代码
```

**过度工程防护机制**：

- **编译期**：`ts-prune` 死代码检测（CI 自动运行）
- **运行时**：文件大小门禁（>800 警告，>1200 阻止）
- **设计期**：七级决策阶梯前置（AGENTS.md 强制加载）
- **不做**：调用链深度限制、类型/函数预算等硬性限制（会严重限制 AI 能力）

## 十一、Scope 边界（四栏表）

定义在 `.butler/scope-boundaries.json`：

| 栏             | 含义                   | 示例                          |
| -------------- | ---------------------- | ----------------------------- |
| **reads**      | 可读范围               | `packages/**/*.ts`            |
| **writes**     | 可写范围（reads 子集） | `packages/domain/src/**/*.ts` |
| **executes**   | 可执行命令（白名单）   | `pnpm test`, `pnpm typecheck` |
| **off_limits** | 绝对禁区（优先级最高） | `.cursorrules`, `AGENTS.md`   |

## 十二、结构化信息维护原则

### 核心原则：人类不直接维护结构化文件

结构化信息文件（`.butler/*.json`、`DESIGN.md`、`AGENTS.md`、`.cursorrules`）应由 AI 工具根据人类意图自动生成，人类仅通过可视化反馈进行确认。

**工作流**：

```
人类意图（自然语言）
  → AI 生成结构化信息（DESIGN.md / AGENTS.md / .cursorrules / .butler/*.json）
  → AI 生成可视化（架构图、依赖图、四栏表可视化）
  → 人类通过视觉确认
  → AI 调整
  → 确认后写入文件
```

**设计理由**：

- 将不确定性语义转化封装在 AI 交互层，后端服务保持无状态
- 天然适配 FC/IS：交互层是外壳，业务逻辑是纯函数核心
- 准确率优先于成本，多轮对话保证转化准确性

### 当前结构化文件清单

| 文件                                  | 用途         | 维护方式               |
| ------------------------------------- | ------------ | ---------------------- |
| `DESIGN.md`                           | 架构设计规范 | AI 生成 + 人类确认     |
| `AGENTS.md`                           | AI 行为契约  | AI 生成 + 人类确认     |
| `.cursorrules`                        | 代码规则     | AI 生成 + 人类确认     |
| `.butler/scope-boundaries.json`       | 安全边界     | AI 生成 + 人类确认     |
| `.butler/load-bearing-marks.json`     | 承重代码     | AI 生成 + 人类确认     |
| `.butler/anti-patterns/registry.json` | 反模式注册   | 自动记录（Owner 触发） |

## 十三、开源集成策略

### 当前已集成

- **Effect-TS**：核心运行时（Effect, Layer, Schema, Schedule, Stream）
- **Drizzle ORM**：数据库层（PostgreSQL）
- **Vitest**：测试框架

### 候选集成（评估中）

| 项目              | 用途                | 优先级 | 评估                                                          |
| ----------------- | ------------------- | ------ | ------------------------------------------------------------- |
| **LangGraph**     | 多 Agent 工作流编排 | 中     | 可替代手写 `application/` 编排，但需评估与 Effect-TS 的兼容性 |
| **Temporal**      | 长时间运行工作流    | 低     | 适合 `delegate_task` 场景，但引入运维复杂度                   |
| **OpenTelemetry** | 可观测性（防线 8）  | 高     | 标准化的 traces/metrics/logs，替代手写 `Effect.logInfo`       |

**集成原则**：

- 优先使用 Effect-TS 生态（已内置重试、并发、流、配置）
- 引入新依赖需通过七级决策阶梯
- 外部依赖必须通过 Port 接口隔离（不直接依赖具体实现）

## 十四、ContextGraph 构想（设计阶段）

将所有压缩、遮蔽、汇总建模为图上的可追溯 mutation：

- 脱敏工具输出不修改原节点，而产生新 `MaskedTool` 节点
- 通过 `replacesId` 指回原节点
- 任意当前节点可 O(1) 反查到原始节点

**状态**：设计阶段，尚未实现。当前使用 `makeContextWindow` + `chooseStrategy` 的简化版本。

## 十五、受保护文件

| 文件                              | 原因            | 修改方式                   |
| --------------------------------- | --------------- | -------------------------- |
| `packages/domain/src/errors.ts`   | 全局错误 ADT    | 人工 + `[MANUAL-OVERRIDE]` |
| `packages/ports/src/index.ts`     | Effect Tag 接口 | 人工 + 契约测试            |
| `.cursorrules`                    | AI 守卫自身     | 人工                       |
| `AGENTS.md`                       | 行为契约        | 人工                       |
| `.butler/scope-boundaries.json`   | 安全边界        | 人工                       |
| `.butler/load-bearing-marks.json` | 承重代码        | 人工                       |

## 十六、开发环境

```bash
pnpm install          # 安装依赖
pnpm typecheck        # 8 包类型检查
pnpm test             # 运行全部测试（3141+）
pnpm lint             # 代码规范检查
pnpm deadcode         # 死代码检测
pnpm format:check     # 格式化检查
pnpm gate             # 完整门禁（typecheck-gate + test）

# 按层级运行测试
bash scripts/run-test-layer.sh domain
bash scripts/run-test-layer.sh guard
```
