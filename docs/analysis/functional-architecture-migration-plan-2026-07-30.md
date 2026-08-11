# Butler v4 函数式架构迁移方案

> **日期**：2026-07-30  
> **目标**：将 Butler v4 从命令式 Python 架构迁移到函数式 TypeScript 架构  
> **核心策略**：绞杀者模式（Strangler Fig）+ FC/IS（Functional Core, Imperative Shell）  
> **技术栈**：TypeScript + Effect-TS + fp-ts + Drizzle ORM  
> **约束**：不中断现有服务、逐模块替换、每步可回滚

---

## 一、可行性分析

### 1.1 结论：**完全可行，但需谨慎分阶段推进**

| 维度 | 评估 | 说明 |
|------|------|------|
| **技术可行性** | ✅ 可行 | Effect-TS/fp-ts 生态成熟，TypeScript 类型系统足够表达代数效应 |
| **业务可行性** | ✅ 可行 | 九层模型已将系统分为独立层，便于逐层替换 |
| **团队可行性** | ⚠️ 需评估 | Effect-TS 学习曲线陡峭，需 2-4 周适应期 |
| **风险等级** | 🔴 高 | 涉及 1,490 文件、12,058 测试用例、微信协议、LLM 调用 |
| **建议** | **分阶段执行** | 不建议全量重写，采用绞杀者模式逐步替换 |

### 1.2 为什么选择函数式架构

当前项目面临的核心痛点，恰好是函数式架构能解决的：

| 当前痛点 | 函数式解决方案 |
|----------|----------------|
| **副作用与业务逻辑混杂** | FC/IS 模式将纯计算与副作用分离 |
| **全局可变状态** | Monad（State/Reader）封装状态，避免共享 |
| **错误处理分散** | Either/Result 链式错误处理，消除 try/except |
| **并发控制复杂** | Effect-TS 的 Fiber 模型统一并发 |
| **测试隔离困难** | 纯函数天然易测，无需 mock |
| **模块间耦合** | 代数效应（Effect）替代隐式依赖注入 |

### 1.3 TypeScript vs Scala 决策

| 维度 | TypeScript + Effect-TS | Scala + ZIO/Cats |
|------|----------------------|-------------------|
| **LLM SDK 支持** | ⭐⭐⭐⭐⭐ OpenAI/Anthropic/MiniMax 原生 TS SDK | ⭐⭐ Scala SDK 需社区维护 |
| **微信协议适配** | ⭐⭐⭐⭐ Node.js HTTP/WebSocket 生态成熟 | ⭐⭐ 需用 Scala HTTP 库重写 |
| **AI 生态工具** | ⭐⭐⭐⭐ LangChain.js, Vercel AI SDK, Zod | ⭐ Scala 生态工具稀少 |
| **类型系统表达力** | ⭐⭐⭐⭐ 支持代数数据类型（ADT）、条件类型 | ⭐⭐⭐⭐⭐ 更强（GADT、高阶类型） |
| **Effect 模型** | ⭐⭐⭐⭐ Effect-TS（< 2.0）已稳定 | ⭐⭐⭐⭐⭐ ZIO/Cats Effect 成熟 |
| **团队学习曲线** | ⭐⭐⭐ 较低（已有 TS 基础即可） | ⭐⭐⭐⭐⭐ 陡峭（需重新学习 Scala） |
| **互操作** | ⭐⭐⭐⭐ 与 Python 通信简单（gRPC/HTTP） | ⭐⭐ 与 Python 通信复杂 |
| **性能** | ⭐⭐⭐ Node.js JIT 足够 | ⭐⭐⭐⭐⭐ Native 编译性能更高 |
| **招聘难度** | ⭐⭐⭐⭐ 易招 TS 开发者 | ⭐⭐⭐ Scala 开发者稀缺 |

#### **决策：选择 TypeScript + Effect-TS**

**核心理由**：
1. **产品就绪度优先**：TS 生态对 LLM SDK、微信协议、向量数据库的支持更成熟
2. **团队可及性**：TS 开发者池子远大于 Scala
3. **渐进迁移友好**：Node.js 可以与 Python 通过 HTTP/gRPC 优雅通信
4. **Effect-TS 已足够**：2.0+ 版本支持 Fiber、Scope、Layer，覆盖所有核心需求

---

## 二、FC/IS 模式映射

### 2.1 FC/IS 核心思想

```
┌─────────────────────────────────────────────────────┐
│              Imperative Shell (命令式外壳)            │
│  • HTTP/微信网关                                     │
│  • 任务调度                                          │
│  • 副作用执行（I/O、数据库、LLM 调用）                 │
│  • 负责：输入校验、事务边界、提交回滚                    │
└───────────────────────┬─────────────────────────────┘
                        │ 调用
                        ▼
┌─────────────────────────────────────────────────────┐
│              Functional Core (函数式核心)              │
│  • 纯函数：无副作用、可预测、可测试                     │
│  • 代数数据类型（ADT）：状态建模                        │
│  • Monad：错误处理、状态传递、并发                      │
│  • 负责：业务逻辑、决策、转换                          │
└─────────────────────────────────────────────────────┘
```

### 2.2 当前代码库 → FC/IS 映射

| 当前层 | 当前代码 | FC/IS 分类 | 迁移目标 |
|--------|----------|------------|----------|
| **contracts/** | Port 接口 + Registry | ✅ 已是函数式核心雏形 | 强化为 Effect Layer |
| **core/agent_loop/** | 命令式循环、try/except | ❌ 命令式 | Effect Gen 链 |
| **core/context_pipeline** | 命令式管线 | ❌ 命令式 | Pipeline + Either |
| **tools/** | 副作用执行 | 🔶 混合 | Shell 层 |
| **gateway/** | I/O、状态变更 | 🔶 混合 | Shell 层 |
| **memory/** | 读写操作 | 🔶 混合 | Effect + Reader |
| **ops/** | 观测/指标 | 🔶 混合 | Stream + Sink |
| **transport/** | HTTP 调用 | ❌ 命令式 | Effect + HttpClient |
| **permissions/** | 纯逻辑判断 | ✅ 纯函数 | 保持 |

### 2.3 目标架构

```
                    ┌──────────────────────────┐
                    │  Imperative Shell Layer   │
                    │  (Node.js Process)        │
                    │                          │
                    │  ┌────────────────────┐  │
                    │  │  Gateway (HTTP/WX)  │  │
                    │  └─────────┬──────────┘  │
                    │            │             │
                    │  ┌─────────┴──────────┐  │
                    │  │   Shell Adapters   │  │
                    │  │  (Effect.run)      │  │
                    │  └─────────┬──────────┘  │
                    └────────────┼─────────────┘
                                 │ Effect Layer
                                 ▼
                    ┌──────────────────────────┐
                    │  Functional Core Layer   │
                    │                          │
                    │  ┌────────────────────┐  │
                    │  │  Agent Loop       │  │
                    │  │  (Effect.gen)     │  │
                    │  └────────────────────┘  │
                    │                          │
                    │  ┌────────────────────┐  │
                    │  │  Context Pipeline │  │
                    │  │  (Pipe + Either)  │  │
                    │  └────────────────────┘  │
                    │                          │
                    │  ┌────────────────────┐  │
                    │  │  Tool Registry    │  │
                    │  │  (Effect + Reader)│  │
                    │  └────────────────────┘  │
                    │                          │
                    │  ┌────────────────────┐  │
                    │  │  Memory System    │  │
                    │  │  (Effect + Drizzle)│  │
                    │  └────────────────────┘  │
                    │                          │
                    │  ┌────────────────────┐  │
                    │  │  Permissions      │  │
                    │  │  (Pure Functions) │  │
                    │  └────────────────────┘  │
                    │                          │
                    │  ┌────────────────────┐  │
                    │  │  Events/CQRS      │  │
                    │  │  (Event Sourcing) │  │
                    │  └────────────────────┘  │
                    └──────────────────────────┘
```

---

## 三、绞杀者模式（Strangler Fig）迁移方案

### 3.1 迁移总览

```
Phase 0          Phase 1          Phase 2          Phase 3          Phase 4
基础设施          观测层            记忆层            工具层            核心层
(Anti-Corruption)  (ops/)          (memory/)        (tools/)         (agent_loop/)
   │                │               │               │               │
   ▼                ▼               ▼               ▼               ▼
 ┌─────┐        ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────────┐
 │ ACL │        │ TS 新   │    │ TS 新   │    │ TS 新   │    │ TS 新       │
 │     │◄──────►│ ops/    │◄──►│ memory/ │◄──►│ tools/ │◄──►│ agent_loop/ │
 └─────┘        └─────────┘    └─────────┘    └─────────┘    └─────────────┘
   │                │               │               │               │
   ▼                ▼               ▼               ▼               ▼
 ┌─────┐        ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────────┐
 │     │        │ Python  │    │ Python  │    │ Python  │    │ Python 老   │
 │     │◄──────►│ 老 ops/ │◄──►│ 老     │◄──►│ 老     │◄──►│ agent_loop/ │
 └─────┘        └─────────┘    └─────────┘    └─────────┘    └─────────────┘
   │                                                                │
   └────────────── 最终：Python 完全淘汰 ──────────────┘
```

### 3.2 Phase 0：基础设施 + 反腐败层（2 周）

#### 3.2.1 搭建 TypeScript 项目骨架

```
butler-ts/
├── package.json
├── tsconfig.json
├── vitest.config.ts
├── src/
│   ├── index.ts                    # 入口
│   ├── core/                       # 函数式核心
│   │   ├── agent-loop/
│   │   ├── context/
│   │   ├── tools/
│   │   └── errors/
│   ├── effects/                    # Effect-TS 基础设施
│   │   ├── layers/                 # Layer 定义
│   │   ├── services/               # Service 接口
│   │   └── runtime/                # Fiber 运行时
│   ├── infrastructure/             # 命令式外壳
│   │   ├── gateway/                # HTTP/微信适配器
│   │   ├── database/               # Drizzle ORM
│   │   ├── llm/                    # LLM 客户端
│   │   └── cache/                  # 缓存适配
│   ├── shared/                     # 共享类型
│   │   ├── types/
│   │   ├── errors/
│   │   └── utils/
│   └── adapters/                   # 与 Python 通信
│       ├── python-bridge.ts        # gRPC/HTTP 桥接
│       └── legacy-client.ts        # 老系统客户端
├── proto/                          # gRPC 协议
│   └── butler.proto
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

#### 3.2.2 反腐败层（Anti-Corruption Layer）

```typescript
// src/adapters/legacy-client.ts
// 反腐败层：在 TS 新系统与 Python 老系统之间建立隔离

interface LegacyService {
  // 仅暴露稳定的 Port 接口，不泄露 Python 内部实现
  readonly healthCheck: Effect.Effect<HealthStatus, LegacyError>
  readonly getMetrics: Effect.Effect<MetricsSnapshot, LegacyError>
  readonly submitEvent: (event: DomainEvent) => Effect.Effect<void, LegacyError>
}

// 通过 gRPC 与 Python 通信
const makeLegacyService = Effect.gen(function* (_) {
  const client = yield* _(grpcClient)
  return {
    healthCheck: Effect.tryPromise({
      try: () => client.HealthCheck({}),
      catch: (e) => new LegacyError(String(e)),
    }),
    getMetrics: Effect.tryPromise({
      try: () => client.GetMetrics({}),
      catch: (e) => new LegacyError(String(e)),
    }),
    submitEvent: (event) => Effect.tryPromise({
      try: () => client.SubmitEvent({ event: serialize(event) }),
      catch: (e) => new LegacyError(String(e)),
    }),
  } satisfies LegacyService
})
```

#### 3.2.3 验收标准

| 标准 | 指标 |
|------|------|
| 项目骨架可构建 | `pnpm build` 成功 |
| Effect-TS 基础测试通过 | 10 个示例测试通过 |
| gRPC 桥接可通信 | TS ↔ Python 双向调用成功 |
| 类型检查零错误 | `tsc --noEmit` 通过 |
| 代码覆盖率 > 80% | 核心模块 |

---

### 3.3 Phase 1：绞杀观测层（ops/）（3 周）

#### 3.3.1 为什么从 ops/ 开始

| 理由 | 说明 |
|------|------|
| **只读居多** | 观测层大部分是读取操作，无副作用 |
| **边界清晰** | 通过 `contracts/` 接口与其他层通信 |
| **风险可控** | 观测失败不影响核心业务 |
| **易于回滚** | 路由回退到 Python 即可 |

#### 3.3.2 迁移步骤

```
Step 1: 定义 TS 版 Port 接口
  │
  ▼
Step 2: 实现 TS 版 Service（函数式核心）
  │   - Effect Layer 定义依赖
  │   - Pure Function 实现业务逻辑
  │
  ▼
Step 3: 实现 Adapter（命令式外壳）
  │   - Drizzle ORM 数据库访问
  │   - Prometheus/OpenTelemetry 集成
  │
  ▼
Step 4: 影子模式（Shadow Mode）
  │   - 同时调用 Python 老系统和 TS 新系统
  │   - 比对结果一致性
  │   - 记录差异日志
  │
  ▼
Step 5: 逐步切换流量
  │   - 1% → 5% → 20% → 50% → 100%
  │   - 每步观察 24 小时
  │
  ▼
Step 6: 切断老系统
```

#### 3.3.3 关键代码示例

```typescript
// src/core/ops/health-service.ts
// 函数式核心：纯业务逻辑

import { Effect, Layer, pipe } from "effect"
import type { HealthStatus, HealthCheckResult } from "../../shared/types/health"

// 代数数据类型（ADT）建模错误
type HealthError =
  | { readonly _tag: "Timeout"; readonly duration: number }
  | { readonly _tag: "DependencyFailed"; readonly dependency: string; readonly reason: string }
  | { readonly _tag: "Degraded"; readonly components: string[] }

// Effect Service 接口（Layer）
export const HealthService = Effect.tag<HealthService>()
export interface HealthService {
  readonly check: () => Effect.Effect<HealthCheckResult, HealthError>
}

// 依赖声明
const makeHealthService = Effect.gen(function* (_) {
  const db = yield* _(Database)
  const metrics = yield* _(MetricsService)

  // 纯函数：组合检查逻辑
  const checks = [
    checkDatabase(db),
    checkMetrics(metrics),
    checkLLM(),
  ]

  const results = yield* _(
    Effect.all(checks, { concurrency: "unbounded" })
  )

  return {
    check: () => {
      const failed = results.filter((r) => r.status === "failed")
      if (failed.length > 0) {
        return Effect.fail({
          _tag: "Degraded",
          components: failed.map((f) => f.component),
        } satisfies HealthError)
      }
      return Effect.succeed({
        status: "healthy",
        components: results,
        timestamp: Date.now(),
      })
    },
  } satisfies HealthService
})

// Layer 绑定依赖
export const HealthServiceLive = Layer.effect(
  HealthService,
  makeHealthService
)
```

#### 3.3.4 验收标准

| 标准 | 指标 |
|------|------|
| 影子模式一致性 | TS/Python 结果差异 < 0.1% |
| 性能不退化 | P99 延迟不超过 Python 的 120% |
| 功能覆盖 | 覆盖所有 ops/ 功能（38 个文件） |
| 测试通过 | TS 单元测试 + 集成测试全部通过 |
| 零故障 | 灰度期间无生产事故 |

---

### 3.4 Phase 2：绞杀记忆层（memory/）（4 周）

#### 3.4.1 挑战

| 挑战 | 解决方案 |
|------|----------|
| **向量存储** | 使用 Drizzle ORM + pgvector（替代 ChromaDB） |
| **嵌入服务** | 保留 fastembed 或迁移到 ONNX Runtime |
| **语义索引** | TS 版语义搜索引擎 |
| **与老系统并行** | 双写 + 异步同步 |

#### 3.4.2 双写策略

```
用户请求 → 写入 TS 新系统 ──→ 立即返回
                │
                └── 异步镜像 ──→ Python 老系统
                                    │
                                    └── 校验一致性
```

```typescript
// src/core/memory/memory-service.ts
// CQRS 分离：写入走命令，读取走查询

// Command 端（写入）
export const MemoryCommands = Effect.tag<MemoryCommands>()
export interface MemoryCommands {
  readonly storeObservation: (input: StoreInput) => Effect.Effect<StoreResult, MemoryError>
  readonly updateVector: (input: UpdateInput) => Effect.Effect<void, MemoryError>
}

// Query 端（读取）
export const MemoryQueries = Effect.tag<MemoryQueries>()
export interface MemoryQueries {
  readonly recall: (input: RecallInput) => Effect.Effect<RecallResult, MemoryError>
  readonly search: (input: SearchInput) => Effect.Effect<SearchResult[], MemoryError>
}
```

#### 3.4.3 验收标准

| 标准 | 指标 |
|------|------|
| 数据一致性 | 双写偏差 < 0.01% |
| 召回质量 | TS 版 Recall 质量 ≥ Python 版 |
| 性能 | 向量搜索 P99 < 50ms |
| 覆盖度 | 覆盖 141 个 memory/ 文件的所有功能 |

---

### 3.5 Phase 3：绞杀工具层（tools/）（4 周）

#### 3.5.1 挑战

| 挑战 | 解决方案 |
|------|----------|
| **工具注册表** | TS 版 ToolRegistry（Effect + Reader） |
| **工具执行** | 部分工具（如 terminal）保持 Python 执行 |
| **Schema 校验** | Zod 替代 Pydantic |

#### 3.5.2 工具执行策略

```typescript
// src/core/tools/tool-registry.ts
// 函数式注册表：不可变、线程安全

// 工具定义（ADT）
type Tool = ReadFile | WriteFile | Patch | SearchFiles | ...

// 工具注册表（Effect + Reader）
const ToolRegistry = Effect.gen(function* (_) {
  const tools = yield* _(RegisteredTools)

  return {
    getTool: (name: string) => Effect.fromNullable(tools.get(name)),
    listTools: () => Effect.succeed(Array.from(tools.values())),
    executeTool: (tool: Tool, input: unknown) =>
      Effect.gen(function* (_) {
        const validator = yield* _(ToolValidator)
        const validated = yield* _(validator.validate(tool, input))
        const executor = yield* _(ToolExecutor)
        return yield* _(executor.execute(tool, validated))
      }),
  }
})
```

#### 3.5.3 验收标准

| 标准 | 指标 |
|------|------|
| 工具兼容性 | 11 内置工具 100% 兼容 |
| 执行正确性 | 工具结果与 Python 版一致 |
| Schema 校验 | Zod 校验覆盖率 100% |
| 并行性能 | 并行工具调度效率 ≥ Python 版 |

---

### 3.6 Phase 4：绞杀核心层（agent_loop/）（6 周）

#### 3.6.1 这是最高风险的阶段

| 风险 | 缓解措施 |
|------|----------|
| 核心逻辑复杂 | 逐子模块替换（context → llm → tools → loop） |
| 状态管理 | State Monad + Event Sourcing |
| 并发模型 | Effect Fiber 模型 |
| 不可回滚 | 保留 Python 版作为 fallback |

#### 3.6.2 Agent Loop 重构

```typescript
// src/core/agent-loop/agent-loop.ts
// 使用 Effect.gen 实现三阶段管线

const agentLoop = (userInput: string) =>
  Effect.gen(function* (_) {
    // 阶段 1: Prepare（上下文准备）
    const prepared = yield* _(prepareContext(userInput))
    
    // 阶段 2: LLM 调用
    const llmResult = yield* _(callLLM(prepared))
    
    // 阶段 3: 工具执行
    const toolResults = yield* _(executeTools(llmResult))
    
    // 迭代直到完成
    if (llmResult.needsMoreTools) {
      return yield* _(agentLoop(userInput))
    }
    
    return llmResult.finalResponse
  })

// Context Pipeline（纯函数）
const prepareContext = (input: string) =>
  Effect.gen(function* (_) {
    const memory = yield* _(MemoryQueries.recall(input))
    const compressed = yield* _(compressContext(memory))
    const sanitized = yield* _(sanitizeMessages(compressed))
    return sanitized
  })

// LLM 调用（Effect 封装副作用）
const callLLM = (messages: Message[]) =>
  Effect.gen(function* (_) {
    const client = yield* _(LLMClient)
    const result = yield* _(client.complete(messages))
    
    // 错误处理：空内容、schema 错误等
    if (isEmptyResponse(result)) {
      return yield* _(retryWithBackoff(callLLM(messages), 3))
    }
    
    return result
  })
```

#### 3.6.3 验收标准

| 标准 | 指标 |
|------|------|
| 对话质量 | LLM 响应质量 ≥ Python 版 |
| 工具调用正确性 | 工具调用成功率 100% |
| 压缩效果 | 上下文压缩率 ≥ Python 版 |
| 并发性能 | 多会话并发处理能力 ≥ Python 版 |
| 端到端 | 完整对话流程 100% 兼容 |

---

## 四、POC 最小验证方案（2 周）

### 4.1 POC 目标

在正式迁移前，用 2 周时间做一个最小 POC，验证：

1. Effect-TS 的错误处理链是否满足需求
2. Effect Fiber 并发模型是否足够
3. TypeScript 类型系统是否足够表达业务模型
4. 与 Python 的 gRPC 通信是否稳定

### 4.2 POC 范围

**实现一个简化版 Agent Loop**：

```
用户输入 → System Prompt + 历史 → LLM 调用 → 工具调度 → 输出
```

### 4.3 POC 交付物

| 交付物 | 说明 |
|--------|------|
| `butler-ts-poc/` | 最小 TS 项目 |
| 简化 Agent Loop | 单线程、3 阶段管线 |
| 1-2 个工具示例 | read_file + search_files |
| Python 桥接示例 | gRPC 调用 Python LLM 客户端 |
| 测试套件 | 20-30 个测试用例 |
| 验证报告 | 性能对比、错误处理验证 |

### 4.4 POC 验收

| 标准 | 通过条件 |
|------|----------|
| 功能正确 | 与 Python 版 Agent Loop 结果一致 |
| 错误处理 | 所有错误路径都有明确类型 |
| 并发能力 | 10 个并发会话无阻塞 |
| 类型安全 | `tsc --noEmit` 零错误 |
| 测试通过 | 所有测试通过 |

---

## 五、技术选型总结

### 5.1 核心技术栈

| 类别 | 选择 | 版本 | 用途 |
|------|------|------|------|
| **语言** | TypeScript | 5.5+ | 主语言 |
| **运行时** | Node.js | 22+ | 执行环境 |
| **函数式库** | Effect-TS | 3.x | Effect 模型、Layer、Fiber |
| **函数式库** | fp-ts | 2.x | 函数式工具（Option/Either/Task） |
| **校验** | Zod | 3.x | Schema 校验（替代 Pydantic） |
| **ORM** | Drizzle | 0.33+ | TypeScript ORM（类型安全） |
| **数据库** | PostgreSQL + pgvector | 16+ | 主存储 + 向量搜索 |
| **HTTP** | Hono | 4.x | HTTP 框架（类型安全） |
| **RPC** | Connect (gRPC-web) | 1.x | TS ↔ Python 通信 |
| **测试** | Vitest | 2.x | 单元/集成测试 |
| **构建** | pnpm + tsup | 9.x | 包管理 + 构建 |
| **容器** | Docker + Compose | — | 部署 |

### 5.2 效果-TS 核心概念对应

| Butler v4 概念 | Effect-TS 对应 |
|---------------|----------------|
| `LoopConfig` | `Effect.Effect<A, E, R>` |
| `LoopCallbacks` | `Effect.Layer` + `Effect.acquireRelease` |
| `tool_batch` | `Effect.all` + `Effect.forEach` |
| `context_pipeline` | `pipe(A, B, C)` 管道组合 |
| `llm_retry` | `Effect.retry` + `Effect.timeout` |
| `tool_guardrails` | `Effect.filter` + `Effect.catchAll` |
| `contracts/ports` | `Effect.tag` + `Effect.Layer` |
| `events.py` | `Effect.stream` + `Sink` |

---

## 六、风险与缓解

### 6.1 高风险项

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **Effect-TS 学习曲线** | 🔴 高 | 中 | 2 周 POC 预研、代码审查、Pair Programming |
| **LLM SDK 兼容性** | 🟡 中 | 高 | 用官方 TS SDK、保留 Python 降级路径 |
| **微信协议重写** | 🔴 高 | 高 | 参考 Python 版、分阶段替换、影子测试 |
| **向量数据迁移** | 🟡 中 | 高 | 双写策略、增量迁移、校验脚本 |
| **性能不达标** | 🟡 中 | 中 | 性能测试先行、保留 Python fallback |

### 6.2 缓解措施

1. **POC 先行**：2 周验证核心假设
2. **影子模式**：每个阶段都有并行运行期
3. **渐进切换**：1% → 100% 流量渐进
4. **自动回滚**：监控告警自动切回 Python
5. **测试双轨**：TS 和 Python 测试并行维护

---

## 七、时间线估算

| 阶段 | 周期 | 产出 |
|------|------|------|
| **Week 1-2** | POC 验证 | 最小 Agent Loop 原型 + 验证报告 |
| **Week 3-4** | Phase 0 | 项目骨架 + 反腐败层 + 基础设施 |
| **Week 5-7** | Phase 1 | ops/ 层迁移（观测层） |
| **Week 8-11** | Phase 2 | memory/ 层迁移（记忆层） |
| **Week 12-15** | Phase 3 | tools/ 层迁移（工具层） |
| **Week 16-21** | Phase 4 | agent_loop/ 层迁移（核心层） |
| **Week 22-24** | 收尾 | 文档完善、性能调优、Python 退役 |

**总计**：约 6 个月（不含 POC 阶段的 2 周）

---

## 八、下一步行动

### 立即执行

1. **[Week 1]** 搭建 `butler-ts-poc/` 最小项目骨架
2. **[Week 1]** 实现简化版 Agent Loop（单轮对话）
3. **[Week 2]** 添加 1-2 个工具，验证工具调度
4. **[Week 2]** 编写验证报告，决定是否全量推进

### 需要的决策

| 决策 | 选项 | 建议 |
|------|------|------|
| 是否接受 6 个月迁移周期 | 是/否 | **建议：是**（长期收益远超短期成本） |
| 是否先做 POC | 是/否 | **建议：是**（2 周验证后再决定） |
| 是否同时维护 Python 代码 | 是/否 | **建议：是**（每个阶段保持 Python 可用） |
| PostgreSQL vs MongoDB | PostgreSQL + pgvector | **建议：PostgreSQL**（Drizzle 生态更好） |

### 需要的资源

| 资源 | 说明 |
|------|------|
| **1 名全职 TS 开发者** | 负责 POC 和架构设计 |
| **1 名兼职 Python 开发者** | 负责反腐败层和 Python 端适配 |
| **每周架构评审** | 跟踪迁移进度和质量 |
| **测试环境** | 独立的 TS 测试环境 |
