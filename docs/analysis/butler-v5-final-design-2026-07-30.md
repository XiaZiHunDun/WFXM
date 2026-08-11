# Butler v5 — 终极设计方案（精简版 · SSOT）

> **日期**：2026-07-30
> **定位**：Butler v5 函数式架构的**单一权威设计文档**（Single Source of Truth）
> **整合来源**：
> - [`butler-v5-complete-design-2026-07-30.md`](butler-v5-complete-design-2026-07-30.md) — 上一版 SSOT（18 条优化建议）
> - [`reference/代码医生方案参考.md`](../../reference/代码医生方案参考.md) — Code Doctor V14.1（2546 行，仅取适配部分）
>
> **本文档优先级最高**：与上述文档冲突时以本文为准。优化建议标 `[OPT-N]`，防错机制标 `[G-N]`。
> **本文精简原则**：摒弃过度工程（详见 §2.3），聚焦 5 个 AI 失败模式 × 10 条精简 GUARD。

---

## 目录

1. [执行摘要](#一执行摘要)
2. [背景与动机](#二背景与动机)
3. [设计原则与范式](#三设计原则与范式)
4. [技术选型](#四技术选型)
5. [架构总览](#五架构总览)
6. [领域模型设计](#六领域模型设计)
7. [端口与服务（Effect Tags）](#七端口与服务effect-tags)
8. [应用层：用例编排](#八应用层用例编排)
9. [基础设施层：命令式外壳](#九基础设施层命令式外壳)
10. [事件溯源 + CQRS](#十事件溯源--cqrs)
11. [网关层（含 Owner 离线策略）](#十一网关层含-owner-离线策略)
12. [配置与可观测性](#十二配置与可观测性)
13. [测试策略](#十三测试策略)
14. [防错机制（10 条 GUARD）](#十四防错机制10-条-guard)
15. [迁移与实施路线图](#十五迁移与实施路线图)
16. [不采纳设计 + 附录](#十六不采纳设计--附录)
17. [开发环境与 CI/CD](#十七开发环境与-cicd)

---

## 一、执行摘要

Butler v5 是对现有 Python v4 的**函数式重写**，采用 **TypeScript + Effect-TS**，核心范式为 **函数式核心 + 命令式外壳（FC/IS）**。

**核心升级**（相对 v4）：

- **领域层零副作用**：业务逻辑为纯函数 + ADT，可单测零 mock
- **副作用显式化**：所有 I/O 包裹在 Effect 中，类型签名声明依赖
- **依赖注入**：Effect Layer 取代 9 个模块级单例
- **事件溯源**：状态变更通过事件流追溯，Hybrid Store 平衡性能与纯度 `[OPT-12]`
- **Spec 驱动开发**：`delegate_task` 接受 Spec 引用而非自由文本 `[OPT-3]`
- **Loop 可中断**：`interrupt/resume` 原语让任意工具可暂停 Loop 等外部输入 `[OPT-2]`
- **Channel 工作流**：多分支并行状态合并由 reducer 自动处理 `[OPT-1]`
- **精简 GUARD 免疫**：10 条精简机制覆盖 v5 真正要补强的 5 类 AI 失败模式 `[G-1..G-10]`

**实施周期**：24 周（约 6 个月），分 5 个 Phase 渐进交付（Phase 0 准备 + Phase 1-4 开发，每 Phase 含 1 周缓冲）。

**与 v4 对比**：

| 维度 | Python v4 | TypeScript v5 |
|------|-----------|---------------|
| 文件数 | 1,490 | ~200（+10 防错守卫） |
| 代码行数 | ~197K | ~32K（+2K 防错层） |
| 测试数 | 12,058 | ~600（+80 守卫测试） |
| 配置项 | 200+ 散落变量 | 1 个 Effect Schema |
| 全局状态 | 9 个模块级单例 | 0（Layer DI） |
| 错误处理 | try/except 散布 | ADT + Effect |
| 并发模型 | threading + 锁 | Fiber |
| AI 失败模式防御 | 仅 PreToolUse hook | 5 类 × 10 条精简机制 |
| 证据门控 | 软提醒 | NO EVIDENCE == NO COMMIT |
| 初始内存 | 15MB（优化后） | <6MB |

---

## 二、背景与动机

### 2.1 v4 的根本问题

| 根本问题 | 表现 | 根因 |
|----------|------|------|
| 副作用与逻辑混杂 | 12,058 个测试需要大量 mock | 没有 FC/IS 分离 |
| 状态不可追踪 | 200+ 全局变量、9 个模块级单例 | 没有事件溯源 |
| 错误处理分散 | try/except 散布在 1,490 个文件 | 没有统一错误 ADT |
| 模块边界模糊 | core/ 299 文件、core→ops 22 处违规导入 | 没有 Layer 依赖注入 |
| 并发控制脆弱 | 线程锁、全局可变状态 | 没有 Fiber 模型 |
| 配置爆炸 | 200+ BUTLER_* 环境变量 | 没有配置 Schema |
| **AI 防错弱** | 仅 PreToolUse + 文件大小守卫 | 没有失败模式矩阵 + 证据门控 |
| **审计绕过** | 黑板交接卡可被 AI 自填 | 没有 Author≠Reviewer + 证据锚定 |

### 2.2 v5 的核心理念

```
┌─────────────────────────────────────────────────────────────────┐
│   纯函数可测试      ←→     副作用可控                              │
│   ADT 让非法状态不可表示      Effect 让副作用可组合                │
│   Event Sourcing 让状态可追溯    Layer 让依赖可替换                │
│   NO EVIDENCE == NO COMMIT      Author ≠ Reviewer                │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 第一性原理与为何不照搬 V14.1

**Butler 项目本质（第一性原理）**：

- **定位**：单人 Owner + 多 AI Agent 的微信编码管家（**不是**企业级多开发者协作系统）
- **核心场景**：Owner 通过微信派编码任务给 AI，AI 在本地代码库执行
- **微信场景特性**：
  - Owner 离线是常态（不是异常），AI 不能假设 Owner 随时响应
  - 微信消息有延迟（秒级），证据门控应异步，不能阻塞主流程
  - Owner 输入不便，应一键确认/拒绝（不是三方辩论 120s）
  - Owner 睡觉时 Butler 空闲，不触发混沌
  - Reviewer 是另一个 AI Agent persona 或 Owner，不是 reviewerPool

**v5 真正要补强的 5 类 AI 失败模式**：

| # | 失败模式 | 现状 |
|---|----------|------|
| 1 | AI 虚假完成（声称已验证但无证据） | v4 只有软提醒 |
| 2 | Owner 离线时 AI 自行推进危险动作 | v4 无策略 |
| 3 | 多文件漏改（只改主文件漏掉链路文件） | v4 PreToolUse 只看单次编辑 |
| 4 | AI 伪造 Owner 确认（黑板卡自填） | v4 无签名校验 |
| 5 | 误删承重代码（删核心模块致系统崩溃） | v4 仅有文件大小守卫 |

**为何不照搬 V14.1 的 32 条机制**：上一版（2914 行）补齐了 V14.1 的 32 条防错机制，但自我评审后发现**严重过度工程**：

| V14.1 原机制 | 过度工程点 | Butler 适配方案 |
|--------------|-----------|----------------|
| 三方辩论（Debate 级 120s） | Owner 微信场景不方便组织辩论 | Owner 微信一键确认/拒绝 |
| L3-L7 自愈层（7 层） | 单人 Owner 项目不需要 7 层 | 3 层：Retry / Fallback / OwnerNotify |
| ChaosService 自适应采样（cpuLoad/ioWait） | Butler 单实例，无集群负载 | 固定每月 1 次 |
| LOC 奖惩因子（多档） | 5 档过细 | 仅"新增 > 预算 3x → WARN" |
| ArchitectureContractLoader 加载 .blackboard/README.md | 黑板规约不需进契约 | 只加载 AGENTS.md + .cursorrules |
| VerifierService / ArbiterService / ChaosService 独立 Tag | 4 个 Tag 维护成本高 | 合并入 1 个 GuardService Tag |
| DeltaChannel V2 双计数器 | 复杂度未匹配场景 | 后置到 P3 |
| FailurePathArchive 自动提案 | AI 自动提案风险 | 改为 Owner 手动触发 |
| 5 张新表 | schema 膨胀 | 2 张表（intent_receipts + load_bearing_marks） |
| reviewerPool 多人假设 | Butler 是单人 Owner | "另一个 AI Agent persona 或 Owner" |
| TypeEscapeLinter 钻石级 | 开发阻塞 | 降级为标准 lint |
| WorkspaceRaceDetector | Butler 单实例 | 删除 |
| DependencyWatcher + LockfileDriftChecker | 后置收益低 | 后置到 P3 |
| PrivacySanitizer + DynamicFence | 双组件过重 | 简化为 PII 脱敏 |
| WriteThenNotify 独立组件 | 与出站流程重复 | 融入 Outbox Pattern |
| 4 级验证（Fast/Standard/Strict/Debate） | 4 级过细 | 2 级（Fast/Standard） |

**结论**：v5 保留 V14.1 的核心思想（契约加载、证据门控、写审分离、承重防护、混沌演练），但**用 10 条精简机制替代原 32 条**，让代码量与单人 Owner 场景匹配。

---

## 三、设计原则与范式

### 3.1 七条设计原则

1. **非法状态不可表示** — 用 ADT 建模，编译期消除非法状态
2. **纯函数优先** — 业务逻辑零副作用，输入相同→输出相同
3. **副作用显式化** — 所有 I/O 包裹在 Effect，类型签名声明依赖
4. **组合优于继承** — 用 pipe/flatMap 组合，不用类继承
5. **错误是值** — 用 Either/Result 表示错误，不用 throw
6. **不可变优先** — 数据用 readonly，状态变更通过事件
7. **NO EVIDENCE == NO COMMIT** — 每次写动作必须留存可验证证据 `[G-1]`

> **注意**：v5 不将"Author ≠ Reviewer"作为独立原则，而是作为 `[G-7]` 角色分离机制实现（见 §14）。Reviewer 在微信场景下可以是另一个 AI Agent persona 或 Owner，不是 reviewerPool。

### 3.2 FC/IS 边界划分

```
┌──────────────────────────────────────────────────────────────────┐
│  Functional Core（domain/）                                       │
│  • ADT 类型定义（LoopState, ToolCall, Observation, IntentReceipt）│
│  • 纯函数（transition, policy, chooseStrategy, verifyEvidence）   │
│  • 零依赖、零副作用，可单测零 mock                                │
│  • 不可变数据（readonly），状态变更通过事件                       │
│  • 含防错纯函数：契约校验、证据完整性计算、删除风险评估            │
└──────────────────────────────────────────────────────────────────┘
                          ↑ 依赖方向单向
┌──────────────────────────────────────────────────────────────────┐
│  Imperative Shell（application/ + infrastructure/ + apps/）       │
│  • Effect.gen 组合业务流程                                        │
│  • Layer 依赖注入（DB, LLM, MCP, WeChat, Guard...）              │
│  • I/O 副作用（数据库、HTTP、文件、微信 API、证据存储）          │
│  • Fiber 并发、Schedule 重试、Stream 事件流                       │
│  • 防错守卫：GuardServiceLive 实现契约加载、多文件校验、自愈     │
└──────────────────────────────────────────────────────────────────┘
```

**判定规则**：能写成纯函数的就放 `domain/`；必须做 I/O 的放 `application/`（编排）或 `infrastructure/`（实现）。防错机制的纯函数部分（契约解析、证据完整性计算、删除风险评分）放 `domain/guards/`，副作用部分（实际 I/O、Hook 执行）放 `infrastructure/guards/`。

### 3.3 ADT 建模约定

```typescript
// 所有 union 类型用 _tag 区分
export type X =
  | { readonly _tag: "CaseA"; readonly field: string }
  | { readonly _tag: "CaseB"; readonly count: number }

// 所有字段 readonly
// 禁止 optional + null，用 Option<T> 或可辨识 union
```

### 3.4 错误是值

```typescript
// 禁止 throw
export type LoopError =
  | { readonly _tag: "LLMUnavailable"; readonly provider: string }
  | { readonly _tag: "ContextOverflow"; readonly tokens: number }
  | { readonly _tag: "ToolFailed"; readonly toolId: string; readonly cause: string }
  | { readonly _tag: "GuardRejected"; readonly reason: GuardReason }  // [G-1..G-10]

// Effect 中用 Effect.fail
yield* Effect.fail({ _tag: "GuardRejected", reason: { _tag: "MissingEvidence" } })
```

### 3.5 证据锚定约定 `[G-1]`

任何 `delegate_task` 完成的写动作都必须留下 `IntentReceipt`：

```typescript
export type IntentReceipt = {
  readonly id: string
  readonly intent: string                    // "添加登录按钮"
  readonly evidenceFiles: readonly string[] // 实际改动的文件
  readonly locDelta: { readonly added: number; readonly removed: number }
  readonly chainCompleteness: number         // 0~1，多文件链路完整度 [G-5]
  readonly guardFindings: readonly GuardFinding[]  // 守卫发现
  readonly authorAgent: string              // 写作 Agent id
  readonly reviewerAgent?: string            // 审查 Agent id（仲裁后填）[G-7]
  readonly ownerApprovalSig?: string        // Owner 签名（涉及承重代码时）[G-4]
  readonly createdAt: number
}
```

> **精简说明**：相比原版，去掉了 `privacyAudit` 字段（PII 脱敏作为标准 lint 步骤，不入 receipt）、`chainCompleteness` 保留（多文件链路校验是 G-5 核心）。

### 3.6 Scope 边界四栏表 `[NEW-OPT-19]`

**模式来源**：GitNexus（78 项目调查 §2.3）。让 AI 明确知道"哪些文件可以改、哪些绝对不能碰"，替代当前简单的 PROTECTED_FILES 列表。

```typescript
// .butler/scope-boundaries.json（AGENTS.md 同步加载）
{
  "reads":  ["src/**/*", "docs/**/*", "tests/**/*", "package.json"],
  "writes": ["src/**/*.ts", "tests/**/*.test.ts", "docs/**/*.md"],
  "executes": ["bun run build", "bun run test", "pnpm typecheck"],
  "off_limits": [
    "butler/core/agent_loop/loop.py",  // 受保护文件
    ".github/workflows/*",              // CI 配置
    "scripts/ai_guard/*",               // AI 守卫自身
    ".blackboard/README.md"             // 交接规约
  ]
}
```

> **四栏语义**：reads=可读范围、writes=可写范围（子集）、executes=可执行命令（白名单）、off_limits=绝对禁区（即使 reads 包含也不可读）。`off_limits` 覆盖 `reads` 和 `writes`，优先级最高。

### 3.7 历史反模式注册表 `[NEW-OPT-20]`

**模式来源**：lobehub（`common-mistakes.md`，L-001 格式）。把历史上踩过的坑固化成反模式清单，每条附 fix commit hash，让 AI 不再重蹈覆辙。

```typescript
// .butler/anti-patterns/registry.json
[
  {
    "id": "L-001",
    "pattern": "Router 双配置不同步 → 404",
    "fix": "e3a1b2c",
    "files": ["desktopRouter.ts", "webRouter.ts"],
    "guard": "pre-commit check-router-sync.sh",
    "date": "2026-03-15"
  },
  {
    "id": "L-002",
    "pattern": "删除 tui/src/memory.rs → 状态持久化崩溃",
    "fix": "f7d8e9a",
    "files": ["tui/src/memory.rs"],
    "guard": "load-bearing-marks.json 标记",
    "date": "2026-04-02"
  }
]
```

> **加载时机**：GuardService.loadContract() 同时加载 registry.json。AI 在每次迭代前读到反模式清单，避免重复历史错误。

### 3.8 七级决策阶梯 `[NEW-OPT-24]`

**模式来源**：Ponytail（The Ladder）。要求 Agent 在写代码之前依次检查，在第一个满足的阶梯停下：

```
1. YAGNI        — 这个需求真的需要实现吗？
2. 代码库复用    — 是否已有类似实现？
3. 标准库       — 标准库是否已提供？
4. 原生平台     — 平台原生功能是否已覆盖？
5. 已安装依赖   — 已安装的依赖是否能解决？
6. 一行代码     — 能否用一行代码解决？
7. 最小实现     — 最后才写最小可用代码
```

> **量化成果**（Ponytail 基准）：代码减少 54%、Token 减少 22%、成本减少 20%、安全 100% 保持。此阶梯写入 AGENTS.md 的 Core Operating Behaviors，作为 Agent 的编码行为准则。Butler 场景下，Agent 在生成代码前先检查阶梯，避免过度工程。

---

## 四、技术选型

### 4.1 核心技术栈

| 层 | 技术 | 版本 | 理由 |
|----|------|------|------|
| 语言 | TypeScript | 5.4+ | 类型安全 + 生态成熟 |
| 运行时 | Node.js | 20 LTS | 长期支持（Bun 1.1+ 可选，原生 TS 更快） |
| 函数式框架 | Effect-TS | 3.x | 内置 Layer/Stream/Schedule，等价 ZIO |
| ORM | Drizzle | 0.30+ | 类型安全 SQL，无 Active Record |
| 数据库 | PostgreSQL | 16 | JSONB + 事务 + LISTEN/NOTIFY（替代 Redis） |
| 事件存储 | Hybrid EventStore | 自研 | 事件流 + Snapshot 平衡 `[OPT-12]` |
| 消息队列 | ~~Redis Stream~~ | — | 单实例不需外部 MQ；用 PostgreSQL LISTEN/NOTIFY + in-process EventBus |
| LLM SDK | @anthropic-ai/sdk + openai | latest | 多 provider 抽象 |
| 测试 | Vitest | 1.x | 原生 ESM + Effect 兼容 |
| 包管理 | pnpm | 9.x | Monorepo workspace |

### 4.2 为什么选 Effect-TS 而非 fp-ts

- **Layer 原生支持**：fp-ts 的 Reader Monad 需手写组合；Effect Layer 内置 DI
- **Fiber 并发**：fp-ts 无内置并发模型；Effect Fiber 等价 ZIO Fiber
- **Schedule 重试**：fp-ts 需手写；Effect Schedule 内置指数退避、抖动
- **Stream**：fp-ts Observable 弱；Effect Stream 与 Fiber 集成
- **Tracing**：Effect.withSpan 自动埋点 `[OPT-17]`
- **生态**：@effect/schema、@effect/rpc、@effect/platform

### 4.3 为什么不用 Scala + ZIO

- 单语言团队成本：Node.js 生态覆盖微信 SDK、微信侧 webhook
- Effect-TS 已提供 ZIO 90% 能力，足够 Butler 场景
- 部署复杂度：JVM 启动慢、镜像大

### 4.4 为什么不引入 WASM / Python 子进程网关

- WASM 沙箱部署复杂，dev_engine 用进程级隔离即可
- v5 完全重写，不需要兼容 v4 Python 网关

---

## 五、架构总览

### 5.1 Monorepo 结构

```
butler-v5/
├── apps/
│   ├── wechat-gateway/      # 微信入站 + 出站
│   └── api/                # HTTP API（管理 + Webhook）
├── packages/
│   ├── domain/             # 纯函数 + ADT（零依赖）
│   │   ├── conversation/
│   │   ├── tools/
│   │   ├── memory/
│   │   ├── workflows/
│   │   ├── projects/
│   │   ├── permissions/
│   │   ├── guards/         # 防错纯函数（精简）
│   │   └── errors.ts
│   ├── application/        # 用例编排（Effect）
│   │   ├── run-loop/
│   │   ├── run-workflow/
│   │   ├── dream/          # 记忆巩固 [OPT-7]
│   │   └── delegate-task/
│   ├── infrastructure/     # 副作用实现
│   │   ├── persistence/    # Drizzle + EventStore
│   │   ├── llm/            # LLM 客户端 + 重试
│   │   ├── mcp/            # MCP 动态发现 [OPT-6]
│   │   ├── wechat/         # 微信 SDK 封装
│   │   └── guards/         # GuardServiceLive（单 Tag）
│   ├── ports/              # 接口定义（Effect Tag）
│   ├── config/             # 单 Schema [OPT-5]
│   └── shared/             # 跨包工具
├── pnpm-workspace.yaml
└── tsconfig.base.json
```

### 5.2 包依赖规则

```
apps/* → application/, ports/, config/
application/ → ports/, domain/
infrastructure/ → ports/, domain/, config/
ports/ → domain/  （只依赖类型）
domain/ → （无依赖，纯 TS）
config/ → domain/  （只读类型）
```

**禁止依赖**：
- `domain/` 不依赖任何包
- `ports/` 不依赖 `application/` 或 `infrastructure/`
- `infrastructure/` 不依赖 `application/`（反向依赖）
- 所有包不直接依赖 `apps/`

### 5.3 包职责详表

| 包 | 职责 | 主要导出 |
|----|------|----------|
| `domain` | ADT + 纯函数 | types, transitions, policies |
| `ports` | Effect Tag 接口 | LLMService, GuardService, ... |
| `application` | 用例编排 | runLoop, runWorkflow, delegateTask |
| `infrastructure` | 副作用实现 | GuardServiceLive, DrizzleEventStore |
| `config` | 单 Schema | ConfigSchema, loadConfig |
| `apps/wechat-gateway` | 微信入站 + 出站 | startGateway |
| `apps/api` | HTTP API | startApi |

---

## 六、领域模型设计

### 6.1 对话域（Conversation）

```typescript
// domain/conversation/types.ts
export type ConversationId = string & { readonly __brand: "ConversationId" }
export type MessageRole = "user" | "assistant" | "tool" | "system"

export type Message = {
  readonly id: string; readonly conversationId: ConversationId
  readonly role: MessageRole; readonly content: string
  readonly toolCalls?: readonly ToolCall[]; readonly toolCallId?: string
  readonly createdAt: number
}

// 对话状态机（精简，去掉 Debate 级）
export type ConversationState =
  | { readonly _tag: "Idle" }
  | { readonly _tag: "Running"; readonly loopId: string }
  | { readonly _tag: "AwaitingToolResult"; readonly toolCallId: string }
  | { readonly _tag: "AwaitingOwnerInput"; readonly prompt: string; readonly since: number }  // [G-3] Owner 离线
  | { readonly _tag: "AwaitingReview"; readonly receiptId: string; readonly reviewerAgent: string }  // [G-7]
  | { readonly _tag: "Completed"; readonly receipt?: IntentReceipt }  // [G-1] 完成携带证据
  | { readonly _tag: "Failed"; readonly error: LoopError; readonly receipt?: IntentReceipt }

// AgentPersona 三元组 [OPT-10]
export type AgentPersona = {
  readonly role: "Coder" | "Reviewer" | "Arbiter"
  readonly name: string; readonly systemPrompt: string; readonly model: string
}

// 上下文压缩 [OPT-8] + 双策略
export type ContextWindow = {
  readonly tokens: number; readonly maxTokens: number
  readonly compressed: boolean; readonly summary?: string
}
export function chooseStrategy(window: ContextWindow): "summarize" | "truncate" {
  if (window.tokens > window.maxTokens * 0.9) return "summarize"
  if (window.tokens > window.maxTokens * 0.7) return "truncate"
  return "summarize"  // 默认安全
}

// ContextGraph 有向图 [OPT-16]
export type ContextNode = {
  readonly id: string
  readonly type: "message" | "tool_call" | "tool_result" | "summary"
  readonly refs: readonly string[]
}

// 状态转移：纯函数（节选关键 case）
export function transition(state: ConversationState, event: ConversationEvent): ConversationState {
  switch (event._tag) {
    case "ToolCallStarted":
      return state._tag === "Running" ? { _tag: "AwaitingToolResult", toolCallId: event.toolCallId } : state
    case "OwnerInputReceived":
      // 注意：loopId 由 application 层生成并传入事件，纯函数不产生副作用
      return state._tag === "AwaitingOwnerInput" && event.loopId
        ? { _tag: "Running", loopId: event.loopId }
        : state
    case "OwnerInputTimeout":  // [G-3] Owner 离线超时
      return state._tag === "AwaitingOwnerInput"
        ? { _tag: "Failed", error: { _tag: "GuardRejected", reason: { _tag: "OwnerOfflineTimeout" } } }
        : state
    // ... 其他 case（ReviewRequested/ReviewCompleted/ConversationCompleted 等）
    default: return state
  }
}

export type ConversationEvent =
  | { readonly _tag: "ConversationStarted"; readonly conversationId: ConversationId }
  | { readonly _tag: "MessageAdded"; readonly message: Message }
  | { readonly _tag: "ToolCallStarted"; readonly toolCallId: string }
  | { readonly _tag: "ToolCallCompleted"; readonly toolCallId: string; readonly result: unknown }
  | { readonly _tag: "OwnerInputReceived"; readonly loopId: string }  // loopId 由 application 层生成
  | { readonly _tag: "OwnerInputTimeout" }
  | { readonly _tag: "ReviewRequested"; readonly receiptId: string; readonly reviewerAgent: string }
  | { readonly _tag: "ReviewCompleted"; readonly receiptId: string; readonly approved: boolean }
  | { readonly _tag: "ConversationCompleted"; readonly receipt?: IntentReceipt }
  | { readonly _tag: "ConversationFailed"; readonly error: LoopError; readonly receipt?: IntentReceipt }
```

### 6.2 工具域（Tools）

```typescript
// domain/tools/types.ts
export type ToolId = string & { readonly __brand: "ToolId" }

export type Tool = {
  readonly id: ToolId; readonly name: string; readonly description: string
  readonly inputSchema: JSONSchema   // [OPT-5] 工具 Schema 自动转 JSON Schema
  readonly outputSchema: JSONSchema
  readonly isGenerated?: boolean      // 标记生成文件工具 [G-2] 承重防护前置判断
  readonly category: "read" | "write" | "execute" | "delegate"
}

export type ToolCall = {
  readonly id: string; readonly toolId: ToolId
  readonly input: unknown; readonly traceId: string  // [OPT-17] 追踪链
}

export type ToolResult = {
  readonly toolCallId: string; readonly success: boolean
  readonly output: unknown; readonly error?: ToolError; readonly durationMs: number
}

// ToolError 携带修复建议
export type ToolError = {
  readonly _tag: string; readonly message: string
  readonly fixSuggestion?: string  // 例："检查文件路径是否存在，或使用 read_file 先确认"
}

// 工具自动发现 [OPT-15]
export type DiscoveredTool = {
  readonly name: string; readonly source: "mcp" | "local" | "delegate"; readonly mcpServer?: string
}
```

### 6.3 记忆域（Memory）

```typescript
// domain/memory/types.ts
export type MemoryId = string & { readonly __brand: "MemoryId" }

export type MemoryRecord = {
  readonly id: MemoryId; readonly content: string; readonly embedding: readonly number[]
  readonly metadata: {
    readonly source: "conversation" | "code" | "doc" | "dream"
    readonly createdAt: number; readonly importance: number  // 0~1
  }
}

// Dream 两阶段 [OPT-7]
export type DreamPhase = "consolidate" | "consolidate-deep"
export type DreamResult = {
  readonly newMemories: readonly MemoryRecord[]
  readonly prunedIds: readonly MemoryId[]; readonly phase: DreamPhase
}
```

### 6.4 工作流域（Workflows）

```typescript
// domain/workflows/types.ts
export type WorkflowId = string & { readonly __brand: "WorkflowId" }

// Channel 抽象 [OPT-1]
export type Channel<T> = { readonly id: string; readonly state: T; readonly suspended: boolean }

// 变更类型分类 [OPT-4]
export type ChangeType =
  | { readonly _tag: "Added"; readonly path: string }
  | { readonly _tag: "Modified"; readonly path: string; readonly diff: string }
  | { readonly _tag: "Removed"; readonly path: string; readonly reason: string }

// Send API [OPT-11]
export type SendCommand = {
  readonly toAgent: string; readonly message: string; readonly contextRef?: string
}

// 工作流状态
export type WorkflowState =
  | { readonly _tag: "NotStarted" }
  | { readonly _tag: "Running"; readonly channels: readonly Channel<unknown>[] }
  | { readonly _tag: "AwaitingMerge"; readonly results: readonly unknown[] }
  | { readonly _tag: "Completed"; readonly outputs: readonly unknown[] }
  | { readonly _tag: "Failed"; readonly error: LoopError }
```

### 6.5 项目域（Projects）

```typescript
// domain/projects/types.ts
export type ProjectId = string & { readonly __brand: "ProjectId" }

export type Project = {
  readonly id: ProjectId; readonly name: string; readonly rootPath: string
  readonly specRef?: string  // [OPT-3] Spec SDD 引用
  readonly createdAt: number
}

// Spec SDD 四制品 [OPT-3]
export type Spec = {
  readonly id: string; readonly project: ProjectId
  readonly documents: {
    readonly spec: string       // requirements.md
    readonly design: string    // design.md
    readonly tasks: string     // tasks.md
    readonly plan: string      // plan.md
  }
  readonly createdAt: number; readonly updatedAt: number
}

// delegate-task 用 Spec 引用
export type DelegateTaskInput = {
  readonly projectId: ProjectId
  readonly specRef: string     // 强制 Spec 引用，不接受自由文本 [OPT-3]
  readonly constraints?: readonly string[]
}
```

### 6.6 权限域（Permissions）

```typescript
// domain/permissions/types.ts
export type Permission =
  | { readonly _tag: "ReadFile"; readonly path: string }
  | { readonly _tag: "WriteFile"; readonly path: string; readonly reason: string }  // reason 强制
  | { readonly _tag: "ExecuteCommand"; readonly command: string }
  | { readonly _tag: "Delegate"; readonly toAgent: string }
  | { readonly _tag: "ModifyLoadBearing"; readonly path: string; readonly ownerApprovalSig: string }  // [G-2] 承重代码

// 承重代码标记 [G-2]
export type LoadBearingMark = {
  readonly path: string; readonly reason: string          // 为什么承重
  readonly markedBy: "owner" | "ai-suggested" | "auto-detected"
  readonly ownerApproved: boolean                         // 必须为 true 才生效
  readonly alternatives?: readonly string[]              // 替代方案提示
}

// 权限决策：纯函数
export function decidePermission(
  perm: Permission, marks: readonly LoadBearingMark[]
): "allow" | "deny" | "require-owner-approval" {
  if (perm._tag === "WriteFile") {
    if (marks.find(m => m.path === perm.path && m.ownerApproved)) return "require-owner-approval"
  }
  if (perm._tag === "ModifyLoadBearing" && !perm.ownerApprovalSig) return "deny"  // 签名校验由 GuardService 完成
  return "allow"
}
```

### 6.7 错误 ADT（全局）+ 修复建议

```typescript
// domain/errors.ts
export type LoopError =
  | { readonly _tag: "LLMUnavailable"; readonly provider: string }
  | { readonly _tag: "ContextOverflow"; readonly tokens: number }
  | { readonly _tag: "ToolFailed"; readonly toolId: string; readonly cause: string }
  | { readonly _tag: "GuardRejected"; readonly reason: GuardReason }
  | { readonly _tag: "OwnerOfflineTimeout"; readonly since: number }
  | { readonly _tag: "WorkflowFailed"; readonly workflowId: string; readonly cause: LoopError }
  | { readonly _tag: "PersistenceFailed"; readonly operation: string; readonly cause: string }

// GuardReason 子类型（对应 10 条 GUARD）
export type GuardReason =
  | { readonly _tag: "MissingEvidence" }                                // [G-1]
  | { readonly _tag: "LoadBearingTouched"; readonly path: string }       // [G-2]
  | { readonly _tag: "OwnerOffline"; readonly action: string }           // [G-3]
  | { readonly _tag: "InvalidHumanSig"; readonly field: string }         // [G-4]
  | { readonly _tag: "ChainIncomplete"; readonly missing: readonly string[] }  // [G-5]
  | { readonly _tag: "VerificationLevelNotMet"; readonly required: "Fast" | "Standard" }  // [G-6]
  | { readonly _tag: "RoleConflict"; readonly author: string; readonly reviewer: string }  // [G-7]
  | { readonly _tag: "HealFailed"; readonly layer: "retry" | "fallback" | "owner-notify" }  // [G-8]
  | { readonly _tag: "AntiPatternDetected"; readonly pattern: string }   // [G-9]
  | { readonly _tag: "ChaosFailure"; readonly scenario: string }          // [G-10]

// 错误 → 修复建议（纯函数，节选关键 case）
export function toFixSuggestion(err: LoopError): string {
  if (err._tag === "LLMUnavailable")
    return `Provider ${err.provider} 不可用，已触发 Retry/Fallback（[G-8]），如仍失败将通知 Owner`
  if (err._tag === "GuardRejected") switch (err.reason._tag) {
    case "MissingEvidence":    return "缺少 IntentReceipt，请补充 evidenceFiles [G-1]"
    case "LoadBearingTouched": return `修改承重代码 ${err.reason.path} 需 Owner 签名 [G-2][G-4]`
    case "OwnerOffline":       return `Owner 离线，${err.reason.action} 已拒绝/入队 [G-3]`
    case "ChainIncomplete":    return `多文件链路缺失：${err.reason.missing.join(", ")} [G-5]`
    case "RoleConflict":       return `作者 ${err.reason.author} 与审查者 ${err.reason.reviewer} 相同 [G-7]`
    // InvalidHumanSig/VerificationLevelNotMet/HealFailed/AntiPatternDetected/ChaosFailure → default
    default: return "守卫拒绝，请查看 GuardFinding 详情"
  }
  return "未知错误，请查看日志"
}
```

### 6.8 防错域（精简 GUARD ADT）

```typescript
// domain/guards/types.ts

// IntentReceipt（精简）[G-1]
export type IntentReceipt = {
  readonly id: string
  readonly intent: string
  readonly evidenceFiles: readonly string[]
  readonly locDelta: { readonly added: number; readonly removed: number }
  readonly chainCompleteness: number
  readonly guardFindings: readonly GuardFinding[]
  readonly authorAgent: string
  readonly reviewerAgent?: string
  readonly ownerApprovalSig?: string
  readonly createdAt: number
}

// GuardFinding：守卫发现汇总
export type GuardFinding = {
  readonly guard: G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10
  readonly status: "pass" | "warn" | "fail"
  readonly detail: string
}

export type G1 = "intent-receipt"
export type G2 = "load-bearing"
export type G3 = "owner-offline-policy"
export type G4 = "human-sig"
export type G5 = "multi-file-chain"
export type G6 = "verification-level"
export type G7 = "role-separation"
export type G8 = "self-heal"
export type G9 = "anti-pattern-archive"
export type G10 = "chaos-drill"

// 2 级验证（替代原 4 级）[G-6]
export type VerificationLevel = "Fast" | "Standard"

export function pickVerificationLevel(
  locDelta: { added: number; removed: number },
  isGeneratedTool: boolean
): VerificationLevel {
  // Fast：augment 工具 + LOC < 50
  if (isGeneratedTool && locDelta.added < 50) return "Fast"
  return "Standard"
}

// 多文件链路校验（纯函数）[G-5]
export type LinkedFilesSpec = {
  readonly mainFile: string
  readonly expectedLinks: readonly string[]  // 例：修改 .tsx 时应同步 .test.tsx
}

export function verifyChain(spec: LinkedFilesSpec, evidenceFiles: readonly string[]) {
  const hit = evidenceFiles.filter(f => spec.expectedLinks.includes(f))
  const missing = spec.expectedLinks.filter(f => !evidenceFiles.includes(f))
  return { completeness: hit.length / spec.expectedLinks.length, missing }
}

// 3 层自愈选择（纯函数）[G-8]
export type HealLayer = "retry" | "fallback" | "owner-notify"

export function pickHealLayer(error: LoopError, retryCount: number): HealLayer {
  if (retryCount < 2 && error._tag !== "GuardRejected") return "retry"
  if (error._tag === "LLMUnavailable" || error._tag === "ToolFailed") return "fallback"  // 切换 provider/工具
  return "owner-notify"  // 兜底：通知 Owner
}

// 删除风险评分（纯函数，依赖 Owner 维护的 LoadBearingMark 配置）[G-2]
export type DeletionRisk = { readonly score: number; readonly reasons: readonly string[] }

export function scoreDeletionRisk(path: string, marks: readonly LoadBearingMark[], locRemoved: number): DeletionRisk {
  const matched = marks.filter(m => m.path === path)
  let score = matched.length > 0 ? 80 : 0
  const reasons = matched.map(m => m.reason)
  if (locRemoved > 100) { score += 20; reasons.push(`删除行数 ${locRemoved} > 100`) }
  return { score: Math.min(score, 100), reasons }
}
```

---

## 七、端口与服务（Effect Tags）

### 7.1 核心服务 Tag

```typescript
// ports/index.ts
// 所有 Tag 用 Context.Tag 模式，签名集中在此处，实现见 infrastructure/

export class LLMService extends Context.Tag("LLMService")<LLMService, {
  readonly complete: (msgs: readonly domain.Message[]) => Effect.Effect<domain.Message, domain.LoopError>
  readonly stream:   (msgs: readonly domain.Message[]) => Stream.Stream<domain.Message, domain.LoopError>
}>() {}

export class EventStoreService extends Context.Tag("EventStoreService")<EventStoreService, {
  readonly append: (streamId: string, events: readonly domain.ConversationEvent[]) => Effect.Effect<void, domain.LoopError>
  readonly load: (streamId: string) => Effect.Effect<readonly domain.ConversationEvent[], domain.LoopError>
  readonly subscribe: () => Stream.Stream<domain.ConversationEvent, never>
}>() {}

export class ToolExecutor extends Context.Tag("ToolExecutor")<ToolExecutor, {
  readonly execute: (call: domain.ToolCall) => Effect.Effect<domain.ToolResult, domain.LoopError>
}>() {}

export class MemoryService extends Context.Tag("MemoryService")<MemoryService, {
  readonly search: (q: string, k: number) => Effect.Effect<readonly domain.MemoryRecord[], never>
  readonly dream: (phase: domain.DreamPhase) => Effect.Effect<domain.DreamResult, never>  // [OPT-7]
}>() {}

export class WorkflowService extends Context.Tag("WorkflowService")<WorkflowService, {
  readonly start: (spec: domain.LinkedFilesSpec) => Effect.Effect<domain.WorkflowId, domain.LoopError>  // [OPT-1]
  readonly send: (cmd: domain.SendCommand) => Effect.Effect<void, domain.LoopError>  // [OPT-11]
  readonly merge: (id: domain.WorkflowId) => Effect.Effect<unknown, domain.LoopError>
}>() {}

export class WeChatGateway extends Context.Tag("WeChatGateway")<WeChatGateway, {
  readonly send: (to: string, msg: string) => Effect.Effect<void, never>
  readonly receive: () => Stream.Stream<{ from: string; content: string }, never>
}>() {}

export class ProjectService extends Context.Tag("ProjectService")<ProjectService, {
  readonly delegateTask: (input: domain.DelegateTaskInput) => Effect.Effect<domain.IntentReceipt, domain.LoopError>
  readonly loadSpec: (ref: string) => Effect.Effect<domain.Spec, domain.LoopError>  // [OPT-3]
}>() {}
```

### 7.2 LoopInterrupt Tag `[OPT-2]`

```typescript
export class LoopInterrupt extends Context.Tag("LoopInterrupt")<
  LoopInterrupt,
  {
    readonly interrupt: (loopId: string, reason: string) => Effect.Effect<void, never>
    readonly resume: (loopId: string, input: unknown) => Effect.Effect<void, never>
    readonly awaitExternal: <A>(prompt: string, timeoutMs: number) => Effect.Effect<A, domain.LoopError>
  }
>() {}
```

### 7.3 GuardService Tag（**单 Tag 合并**）`[G-1..G-10]`

> **精简说明**：原方案有 VerifierService / ArbiterService / ChaosService / ContractLoader 四个独立 Tag，v5 合并为单个 GuardService Tag，减少维护成本。

```typescript
// ports/guards.ts
// 单 Tag 合并：原 Verifier/Arbiter/Chaos/ContractLoader 4 个 Tag → 1 个 GuardService
// 10 个方法对应 [G-1..G-10]，详细语义见 §14.1 总览表与 §9.7 实现
export class GuardService extends Context.Tag("GuardService")<GuardService, {
  readonly issueReceipt: (input: {
    intent: string; evidenceFiles: readonly string[]
    locDelta: { added: number; removed: number }; authorAgent: string
  }) => Effect.Effect<domain.IntentReceipt, domain.LoopError>                              // [G-1]
  readonly checkLoadBearing: (path: string, op: "write" | "delete") => Effect.Effect<       // [G-2]
    { allowed: boolean; mark?: domain.LoadBearingMark }, domain.LoopError>
  readonly checkOwnerOnline: (action: {                    // [G-3]
    toolId: string; category: "read" | "write" | "execute" | "delegate"
  }) => Effect.Effect<{ decision: "allow" | "queue" | "deny"; reason: string }, never>
  readonly verifyHumanSig: (sig: string, payload: unknown) => Effect.Effect<boolean, never> // [G-4]
  readonly verifyChain: (spec: domain.LinkedFilesSpec, files: readonly string[]) => Effect.Effect<  // [G-5]
    { completeness: number; missing: readonly string[] }, never>
  readonly pickVerification: (delta: { added: number; removed: number }, isGen: boolean) => // [G-6]
    Effect.Effect<domain.VerificationLevel, never>
  readonly checkRoleSeparation: (author: string, reviewer: string) =>                      // [G-7]
    Effect.Effect<{ ok: boolean; reason?: string }, never>
  readonly heal: <A, E>(effect: Effect.Effect<A, E>,                                         // [G-8]
    options: { maxRetry: number; fallback?: () => Effect.Effect<A, E> }
  ) => Effect.Effect<A, E | domain.LoopError>
  readonly archiveAntiPattern: (pattern: string, evidence: unknown) => Effect.Effect<void, never>  // [G-9]
  readonly scheduleChaos: (scenario: string, cron: string) => Effect.Effect<void, never>           // [G-10]
  // 契约加载：只加载 AGENTS.md + .cursorrules（不含 .blackboard/README.md）
  readonly loadContract: () => Effect.Effect<ContractSnapshot, never>
}>() {}

export type ContractSnapshot = {
  readonly loadedFiles: readonly string[]  // ["AGENTS.md", ".cursorrules"]
  readonly rules: readonly ContractRule[]; readonly loadedAt: number
}
export type ContractRule = { readonly pattern: string; readonly severity: "WARN" | "BLOCK"; readonly source: string }
```

### 7.4 其他 Tag

```typescript
// MCP 动态发现 [OPT-6]
export class MCPDiscovery extends Context.Tag("MCPDiscovery")<
  MCPDiscovery,
  {
    readonly discover: () => Effect.Effect<readonly domain.DiscoveredTool[], never>
    readonly invalidate: (server: string) => Effect.Effect<void, never>
  }
>() {}

// 配置 [OPT-5]
export class Config extends Context.Tag("Config")<Config, ConfigShape>() {}
```

### 7.5 Layer 组合

```typescript
// infrastructure/layers.ts
export const ProductionLayer = Layer.mergeAll(
  LLMServiceLive,
  DrizzleEventStoreLive,
  ToolExecutorLive,
  MemoryServiceLive,
  WorkflowServiceLive,
  WeChatGatewayLive,
  ProjectServiceLive,
  LoopInterruptLive,
  GuardServiceLive,  // 单一守卫 Layer
  MCPDiscoveryLive,
  ConfigLive,
)
```

### 7.6 Harness 模板系统 `[NEW-OPT-23]`

**模式来源**：OpenInterpreter（Harness 仿真架构，78 项目调查 §2.4）。为不同 LLM 提供商准备不同的 system prompt 模板，自动根据模型选择最优交互协议。

```typescript
// ports/harness.ts
export class HarnessRouter extends Context.Tag("HarnessRouter")<HarnessRouter, {
  readonly selectFor: (model: string) => Effect.Effect<HarnessProfile, never>
  readonly buildRequest: (profile: HarnessProfile, ctx: HarnessCtx) => Effect.Effect<ToolCall[], never>
}>() {}

export type HarnessProfile = {
  readonly name: string          // "claude-code" | "kimi-code" | "deepseek-tui"
  readonly systemPrompt: string  // 专属 system prompt 模板
  readonly toolSchemas: unknown  // 工具集 JSON Schema
  readonly maxTokens: number
  readonly supportsThinking: boolean
}

export type HarnessCtx = {
  readonly messages: readonly Message[]
  readonly tools: readonly Tool[]
  readonly workingDir: string; readonly os: string
}
```

> **自动路由**：根据模型名称自动匹配最优 HarnessProfile（如 DeepSeek → `claude-code-bare`，Kimi → `kimi-code`）。LLMServiceLive 中集成 HarnessRouter，切换 LLM 时自动切换 system prompt 和工具 Schema。

### 7.7 事件驱动调度器 `[NEW-OPT-27]`

**模式来源**：Gemini-CLI（Scheduler 五阶段生命周期）。将当前 Loop 中内嵌的工具调用拆分为结构化的五阶段调度器。

```
调度生命周期：
  1. Ingestion（摄入）   → 接收 LLM 返回的工具调用批次
  2. Validation（验证）  → 参数校验 + Hook 检查 + Guard 策略检查
  3. Confirmation（确认）→ 用户确认流程（allow/deny/ask）
  4. Execution（执行）   → 并行（只读）或顺序（写）执行工具
  5. Finalization（终结）→ 状态更新 + 日志记录 + IntentReceipt
```

```typescript
// ports/scheduler.ts
export class Scheduler extends Context.Tag("Scheduler")<Scheduler, {
  readonly schedule: (calls: readonly ToolCall[]) => Effect.Effect<readonly ToolResult[], LoopError>
  readonly abort: () => Effect.Effect<void, never>
}>() {}

// 并行执行策略：只读工具默认并行，写工具顺序执行
export function classifyCalls(calls: readonly ToolCall[]): { parallel: ToolCall[]; sequential: ToolCall[] } {
  const readTools = new Set(["read_file", "search", "grep", "glob"])
  return {
    parallel: calls.filter(c => readTools.has(c.name)),
    sequential: calls.filter(c => !readTools.has(c.name)),
  }
}
```

---

## 八、应用层：用例编排

### 8.1 对话用例：run-loop（含证据门控）

```typescript
// application/run-loop/run-loop.ts
export const runLoop = (input: {
  conversationId: ConversationId; userMessage: string
}): Effect.Effect<IntentReceipt, LoopError> =>
  Effect.gen(function* (_) {
    const llm = yield* _(LLMService)
    const toolExec = yield* _(ToolExecutor)
    const guard = yield* _(GuardService)
    const interrupt = yield* _(LoopInterrupt)
    let messages: readonly Message[] = [userMsg(input.userMessage)]
    while (true) {
      // 1. LLM 生成（[G-8] 自愈：Retry → Fallback 已在 LLMServiceLive 内置）
      const reply = yield* _(llm.complete(messages))
      // 2. 工具调用：先过守卫再执行
      if (reply.toolCalls && reply.toolCalls.length > 0) {
        for (const call of reply.toolCalls) {
          // [G-3] Owner 离线策略：deny → fail；queue → awaitExternal
          const ownerCheck = yield* _(guard.checkOwnerOnline({ toolId: call.toolId, category: "write" }))
          if (ownerCheck.decision === "deny")
            yield* _(Effect.fail({ _tag: "GuardRejected", reason: { _tag: "OwnerOffline", action: call.toolId } }))
          if (ownerCheck.decision === "queue")
            yield* _(interrupt.awaitExternal("Owner 上线后批准", 24 * 3600 * 1000))
          // [G-2] 承重代码防护 + [G-4] HUMAN 签名
          if (call.toolId === "write_file" || call.toolId === "delete_file") {
            const path = (call.input as { path: string }).path
            const lbCheck = yield* _(guard.checkLoadBearing(path, call.toolId === "delete_file" ? "delete" : "write"))
            if (!lbCheck.allowed && lbCheck.mark) {
              const sig = yield* _(interrupt.awaitExternal<string>(`修改承重代码 ${path}，请提供 HUMAN 签名`, 3600 * 1000))
              const ok = yield* _(guard.verifyHumanSig(sig, { path, mark: lbCheck.mark }))
              if (!ok)
                yield* _(Effect.fail({ _tag: "GuardRejected", reason: { _tag: "InvalidHumanSig", field: "ownerApprovalSig" } }))
            }
          }
          const result = yield* _(toolExec.execute(call))
          messages = [...messages, toToolMessage(result)]
        }
      } else if (isComplete(reply)) {
        // 3. 完成：签发 IntentReceipt [G-1]
        const receipt = yield* _(guard.issueReceipt({
          intent: input.userMessage,
          evidenceFiles: collectEvidenceFiles(messages),
          locDelta: computeLocDelta(messages),
          authorAgent: "claude-3-5-sonnet",
        }))
        // [G-5] 多文件链路校验
        const chainSpec = inferChainSpec(input.userMessage)
        if (chainSpec) {
          const chain = yield* _(guard.verifyChain(chainSpec, receipt.evidenceFiles))
          if (chain.completeness < 1)
            yield* _(Effect.fail({ _tag: "GuardRejected", reason: { _tag: "ChainIncomplete", missing: chain.missing } }))
        }
        // [G-7] 角色分离 + [G-6] 验证级别
        const reviewer = pickReviewer("claude-3-5-sonnet")
        const roleCheck = yield* _(guard.checkRoleSeparation(receipt.authorAgent, reviewer))
        if (!roleCheck.ok)
          yield* _(Effect.fail({ _tag: "GuardRejected", reason: { _tag: "RoleConflict", author: receipt.authorAgent, reviewer } }))
        const level = yield* _(guard.pickVerification(receipt.locDelta, false))
        if (level === "Standard") {
          const approved = yield* _(interrupt.awaitExternal<boolean>(
            `[审查请求] Intent: ${receipt.intent}\n证据文件: ${receipt.evidenceFiles.join(", ")}\n批准？`,
            3600 * 1000
          ))
          if (!approved)
            yield* _(Effect.fail({ _tag: "GuardRejected", reason: { _tag: "VerificationLevelNotMet", required: "Standard" } }))
        }
        return { ...receipt, reviewerAgent: reviewer }
      } else {
        messages = [...messages, reply]
      }
    }
  })
```

### 8.2 工作用例：run-workflow

```typescript
// application/run-workflow/run-workflow.ts
export const runWorkflow = (spec: LinkedFilesSpec): Effect.Effect<WorkflowId, LoopError> =>
  Effect.gen(function* (_) {
    const wf = yield* _(WorkflowService)
    const id = yield* _(wf.start(spec))
    // [OPT-1] Channel 多分支并行
    const channels = spec.expectedLinks.map(file =>
      wf.send({ toAgent: `coder-${file}`, message: `实现 ${file}`, contextRef: id }))
    yield* _(Effect.all(channels, { concurrency: "unbounded" }))
    yield* _(wf.merge(id))   // 合并结果
    return id
  })
```

### 8.3 记忆用例：Dream 两阶段 `[OPT-7]`

```typescript
// application/dream/dream.ts
export const dream = (phase: DreamPhase): Effect.Effect<DreamResult, never> =>
  Effect.gen(function* (_) {
    const mem = yield* _(MemoryService)
    return yield* _(mem.dream(phase))
  })
```

### 8.4 项目用例：delegate-task（含证据留存）

```typescript
// application/delegate-task/delegate-task.ts
export const delegateTask = (input: DelegateTaskInput): Effect.Effect<IntentReceipt, LoopError> =>
  Effect.gen(function* (_) {
    const proj = yield* _(ProjectService)
    const guard = yield* _(GuardService)
    const _spec = yield* _(proj.loadSpec(input.specRef))    // [OPT-3] 强制 Spec 引用
    const receipt = yield* _(proj.delegateTask(input))     // 实际由 Agent 执行
    // [G-1] 证据门控：无证据即失败
    if (receipt.evidenceFiles.length === 0)
      yield* _(Effect.fail({ _tag: "GuardRejected", reason: { _tag: "MissingEvidence" } }))
    return receipt
  })
```

---

## 九、基础设施层：命令式外壳

### 9.1 数据库 + Drizzle

```typescript
// infrastructure/persistence/schema.ts
import { pgTable, text, integer, timestamp, jsonb, boolean } from "drizzle-orm/pg-core"

// 事件流（Event Sourcing 写模型 + 审计）
export const events = pgTable("events", {
  id: text("id").primaryKey(), streamId: text("stream_id").notNull(),
  version: integer("version").notNull(), type: text("type").notNull(),
  payload: jsonb("payload").notNull(), createdAt: timestamp("created_at").notNull().defaultNow(),
})

// 出站消息（Outbox Pattern，双写一致性）
export const outbox = pgTable("outbox", {
  id: text("id").primaryKey(), aggregateId: text("aggregate_id").notNull(),
  type: text("type").notNull(), payload: jsonb("payload").notNull(),
  publishedAt: timestamp("published_at"), createdAt: timestamp("created_at").notNull().defaultNow(),
})

// [G-1] IntentReceipts 表（精简：含 guardFindings JSON）
export const intentReceipts = pgTable("intent_receipts", {
  id: text("id").primaryKey(),
  intent: text("intent").notNull(),
  evidenceFiles: jsonb("evidence_files").notNull(),       // string[]
  locDelta: jsonb("loc_delta").notNull(),                  // {added, removed}
  chainCompleteness: integer("chain_completeness").notNull(),
  guardFindings: jsonb("guard_findings").notNull(),        // GuardFinding[]
  authorAgent: text("author_agent").notNull(),
  reviewerAgent: text("reviewer_agent"),
  ownerApprovalSig: text("owner_approval_sig"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
})

// [G-2] 承重代码标记表
export const loadBearingMarks = pgTable("load_bearing_marks", {
  path: text("path").primaryKey(),
  reason: text("reason").notNull(),
  markedBy: text("marked_by").notNull(),                   // "owner" | "ai-suggested" | "auto-detected"
  ownerApproved: boolean("owner_approved").notNull().default(false),
  alternatives: jsonb("alternatives"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
})
```

> **精简说明**：相比原方案 6 张表，删除 CQRS 读模型（conversations / messages），保留 4 张：events + outbox 为架构表，intent_receipts + load_bearing_marks 为 GUARD 表。读模型直接从事件流投影，查询性能不足时按需引入 PostgreSQL MATERIALIZED VIEW。

### 9.2 LLM 客户端 + 重试

```typescript
// infrastructure/llm/llm-live.ts
export const LLMServiceLive = Layer.effect(LLMService, Effect.gen(function* () {
  const primary = yield* createAnthropicClient()      // 主 provider
  const fallback = yield* createOpenAIClient()        // [G-8] Fallback
  return LLMService.of({
    complete: (messages) =>
      Effect.tryPromise({
        try: () => primary.messages.create({ /* ... */ }),
        catch: () => ({ _tag: "LLMUnavailable", provider: "anthropic" }) as LoopError,
      }).pipe(
        Effect.retry({ times: 2, schedule: Schedule.exponential("1 seconds") }),  // [G-8] Retry
        Effect.catchAll(() => Effect.tryPromise({                                  // [G-8] Fallback
          try: () => fallback.chat.completions.create({ /* ... */ }),
          catch: () => ({ _tag: "LLMUnavailable", provider: "openai" }) as LoopError,
        }))
      ),
    stream: (messages) => Stream.fromIterable(/* ... */),
  })
}))
```

### 9.3 MCP 动态发现 + 缓存失效 `[OPT-6]`

```typescript
// infrastructure/mcp/mcp-discovery-live.ts
export const MCPDiscoveryLive = Layer.effect(MCPDiscovery, Effect.gen(function* () {
  let cache = new Map<string, DiscoveredTool>()
  return MCPDiscovery.of({
    discover: () => Effect.gen(function* () {
      if (cache.size > 0) return Array.from(cache.values())
      const servers = yield* listMCPServers()
      const tools = yield* Effect.all(servers.map(listTools), { concurrency: "unbounded" })
      cache = new Map(tools.flat().map(t => [t.name, t]))
      return tools.flat()
    }),
    invalidate: (server) => Effect.sync(() => {
      for (const [k, v] of cache) if (v.mcpServer === server) cache.delete(k)
    }),
  })
}))
```

### 9.4 Hybrid EventStore（事件 + Snapshot）`[OPT-12]`

```typescript
// infrastructure/persistence/eventstore-live.ts
export const DrizzleEventStoreLive = Layer.effect(EventStoreService, Effect.gen(function* () {
  const db = yield* getDb()
  const snapshotFreq = 50  // 每 50 个事件做一次 Snapshot（替代原 ShadowEngine 独立采样）
  return EventStoreService.of({
    append: (streamId, events) => Effect.gen(function* () {
      yield* db.insert(eventsTable).values(events.map(e => ({
        streamId, version: yield* nextVersion(db, streamId),
        type: (e as { _tag: string })._tag, payload: e, createdAt: new Date(),
      })))
      const total = yield* countEvents(db, streamId)
      if (total % snapshotFreq === 0) yield* saveSnapshot(db, streamId, total)
    }),
    load: (streamId) => Effect.gen(function* () {
      const snap = yield* loadSnapshot(db, streamId)
      const events = yield* db.select().from(eventsTable).where(eq(eventsTable.streamId, streamId))
      return [...(snap ? [snap] : []), ...events.map(parseEvent)]
    }),
    subscribe: () => Stream.fromIterableEmitter(/* pg-listen */),
  })
}))
```

### 9.5 RelativeIndenter + 多策略 patch `[OPT-13]`

```typescript
// infrastructure/patch/relative-indenter.ts
export function applyPatch(content: string, patch: string): string {
  // 1. 尝试 unified diff
  if (patch.startsWith("@@")) return applyUnified(content, patch)
  // 2. 尝试 search-replace
  if (patch.includes("<<<<<<< SEARCH")) return applySearchReplace(content, patch)
  // 3. 兜底：相对缩进插入
  return applyRelativeIndent(content, patch)
}
```

### 9.6 文件重要性评分（替代 PageRank）`[OPT-14]`

```typescript
// infrastructure/patch/repo-map.ts
// 基于目录 + 配置的简单评分（替代 PageRank，200-500 文件规模足够）
export function scoreFileImportance(path: string, marks: readonly LoadBearingMark[]): number {
  let score = 0
  if (path.startsWith("butler/core/")) score += 5            // 核心模块
  if (path.startsWith("butler/gateway/")) score += 3         // 网关层
  if (marks.some(m => m.path === path)) score += 80         // [G-2] 承重标记
  if (path.endsWith(".test.ts") || path.endsWith("_test.py")) score = 0  // 测试文件低优先级
  return score
}
```

### 9.7 GuardServiceLive 实现（**单 Layer 含全部 10 条 GUARD**）

```typescript
// infrastructure/guards/guard-service-live.ts
// 10 个方法对应 [G-1..G-10]，接口签名见 §7.3
export const GuardServiceLive = Layer.effect(GuardService, Effect.gen(function* () {
  const db = yield* getDb()
  const marksCache = yield* loadMarks(db)            // [G-2] 启动缓存承重标记
  let ownerLastSeen = Date.now()                     // [G-3] Owner 心跳
  const archiveDir = ".butler/anti-patterns/"        // [G-9]

  return GuardService.of({
    // [G-1] 签发 IntentReceipt → 写 intent_receipts 表
    issueReceipt: (input) => Effect.gen(function* () {
      const receipt: IntentReceipt = {
        id: crypto.randomUUID(), chainCompleteness: 1, guardFindings: [],
        createdAt: Date.now(), ...input,
      }
      yield* db.insert(intentReceipts).values(receipt)
      return receipt
    }),
    // [G-2] 承重代码：命中且 ownerApproved → 拒绝
    checkLoadBearing: (path) => Effect.sync(() => {
      const mark = marksCache.find(m => m.path === path && m.ownerApproved)
      return mark ? { allowed: false, mark } : { allowed: true }
    }),
    // [G-3] Owner 离线策略（5min queue / 30min deny / 23-07 queue）
    checkOwnerOnline: (action) => Effect.sync(() => {
      if (action.category === "read") return { decision: "allow", reason: "读动作放行" } as const
      const offlineMs = Date.now() - ownerLastSeen
      if (offlineMs > 30 * 60 * 1000) return { decision: "deny", reason: `离线超 30 分钟` } as const
      if (offlineMs > 5 * 60 * 1000)  return { decision: "queue", reason: `离线 ${Math.floor(offlineMs/60000)} 分钟` } as const
      if (isSleepHours())             return { decision: "queue", reason: "睡眠时段" } as const
      return { decision: "allow", reason: "在线" } as const
    }),
    // [G-4] HMAC-SHA256 + 常时比较
    verifyHumanSig: (sig, payload) => Effect.sync(() =>
      timingSafeEqual(sig, hmacSha256(HUMAN_SECRET, JSON.stringify(payload)))
    ),
    // [G-5] 直接调用 domain.verifyChain（纯函数复用）
    verifyChain: (spec, files) => Effect.sync(() => verifyChain(spec, files)),
    // [G-6] 直接调用 domain.pickVerificationLevel
    pickVerification: (delta, isGen) => Effect.sync(() => pickVerificationLevel(delta, isGen)),
    // [G-7] author ≠ reviewer
    checkRoleSeparation: (author, reviewer) => Effect.sync(() =>
      author === reviewer
        ? { ok: false, reason: "作者与审查者不能相同" }
        : { ok: true }
    ),
    // [G-8] 3 层自愈：Retry → Fallback → OwnerNotify（tapError 通知但不改变错误流）
    heal: <A, E>(effect, options) =>
      effect.pipe(
        Effect.retry({ times: options.maxRetry }),
        Effect.catchAll(e => options.fallback ? options.fallback() : Effect.fail(e)),
        Effect.tapError(e => Effect.gen(function* () {
          const wx = yield* WeChatGateway
          yield* wx.send(OWNER_WXID, `[自愈失败] ${(e as LoopError)._tag}，需介入`)
        }))
      ),
    // [G-9] Owner 手动触发归档（AI 无权自动修改 .cursorrules）
    archiveAntiPattern: (pattern, evidence) => Effect.gen(function* () {
      yield* writeJson(`${archiveDir}${pattern}-${Date.now()}.json`, { pattern, evidence })
    }),
    // [G-10] 每月 1 号 3:00 cron 调度
    scheduleChaos: (_, cron) => Effect.schedule(Effect.never, Schedule.cron(cron || "0 3 1 * *")),
    // 契约加载：只加载 AGENTS.md + .cursorrules（不含 .blackboard/README.md）
    loadContract: () => Effect.gen(function* () {
      const files = ["AGENTS.md", ".cursorrules"]
      const rules = yield* Effect.all(files.map(parseRules), { concurrency: "unbounded" })
      return { loadedFiles: files, rules: rules.flat(), loadedAt: Date.now() }
    }),
  })
}))
```

---

## 十、事件溯源 + CQRS

### 10.1 事件流

```typescript
// 事件 → 状态投影（纯函数）
export function projectConversation(events: readonly ConversationEvent[]): ConversationState {
  return events.reduce(transition, { _tag: "Idle" } as ConversationState)
}
```

### 10.2 CQRS 读写分离（简化版）

```typescript
// 保留 Event Sourcing 的事件日志用于审计，读模型直接从事件流投影
// 不维护独立的 conversations / messages 读表（单人场景查询并发极低）
export function loadConversation(events: readonly ConversationEvent[]): ConversationState {
  return events.reduce(transition, { _tag: "Idle" } as ConversationState)
}
// 仅在查询性能不足时（如按日期范围查历史对话）引入 PostgreSQL MATERIALIZED VIEW
```

### 10.3 Outbox Pattern（双写一致性）

```typescript
// 写事件 + 写 Outbox 在同一事务
export const appendWithOutbox = (
  streamId: string,
  events: readonly ConversationEvent[],
  outboxMsg: OutboxMsg
) => Effect.gen(function* () {
  const db = yield* getDb()
  yield* db.transaction(async tx => {
    await tx.insert(eventsTable).values(events.map(/* ... */))
    await tx.insert(outboxTable).values(outboxMsg)
  })
  // Outbox Publisher 单独消费 outboxTable → 微信/HTTP
})
```

> **精简说明**：原方案的 `[GUARD-20] WriteThenNotify` 独立组件**已融入 Outbox Pattern**，不再单独存在。出站消息通过 Outbox 发布器统一处理。

### 10.4 DeltaChannel 增量检查点 `[OPT-12]`

```typescript
// DeltaChannel：基于版本号增量计算
export type DeltaChannel = {
  readonly streamId: string
  readonly lastVersion: number
}

export function delta(channel: DeltaChannel, events: readonly ConversationEvent[]): readonly ConversationEvent[] {
  return events.slice(channel.lastVersion)
}
```

> **精简说明**：原方案的 `[GUARD-19]` DeltaChannel V2 双计数器（counter + ack）后置到 P3 阶段，v5 只保留单计数器版本。

---

## 十一、网关层（含 Owner 离线策略）

### 11.1 入站 EventBus `[OPT-9]`

```typescript
// apps/wechat-gateway/inbound.ts
export const startGateway = Effect.gen(function* () {
  const bus = yield* EventBus
  const wechat = yield* WeChatGateway

  // 微信消息 → EventBus
  yield* wechat.receive().pipe(
    Stream.runForEach(msg => 
      bus.publish({ _tag: "WeChatMessageReceived", from: msg.from, content: msg.content })
    )
  )
})

// 轻量 EventBus
export class EventBus extends Context.Tag("EventBus")<
  EventBus,
  { readonly publish: (e: Event) => Effect.Effect<void, never>; 
    readonly subscribe: () => Stream.Stream<Event, never> }
>() {}
```

### 11.2 出站消息（Outbox 驱动）

```typescript
// apps/wechat-gateway/outbound.ts
export const OutboxPublisher = Effect.gen(function* () {
  const db = yield* getDb()
  const wechat = yield* WeChatGateway

  while (true) {
    const pending = yield* db.select().from(outbox).where(isNull(outbox.publishedAt))
    for (const msg of pending) {
      yield* wechat.send(/* to */, JSON.stringify(msg.payload))
      yield* db.update(outbox).set({ publishedAt: new Date() }).where(eq(outbox.id, msg.id))
    }
    yield* Effect.sleep("5 seconds")
  }
})
```

### 11.3 Owner 离线策略 `[G-3]`

**第一性原理**：Butler 微信场景下 Owner 离线是常态，不能假设 Owner 随时响应。

```typescript
// apps/wechat-gateway/owner-presence.ts
// 心跳：每条 Owner 微信消息更新 ownerLastSeen（由 OwnerPresenceMonitor 订阅）
export const OwnerPresenceMonitor = Effect.gen(function* () {
  const wechat = yield* WeChatGateway
  yield* wechat.receive().pipe(
    Stream.runForEach(msg => { if (msg.from === OWNER_WXID) ownerLastSeen = Date.now(); return Effect.void })
  )
})
```

**Owner 离线策略矩阵**：

| Owner 状态 | 离线时长 | 读动作 | 写动作（非承重） | 写动作（承重） | 委派任务 |
|-----------|---------|--------|----------------|----------------|---------|
| 在线 | < 5 min | allow | allow | require-sig `[G-4]` | allow |
| 短离线 | 5–30 min | allow | queue `[G-3]` | deny | queue |
| 长离线 | > 30 min | allow | deny `[G-3]` | deny | deny |
| 睡眠时段 | 23:00–07:00 | allow | queue（次日处理） | deny | deny |

**关键设计**：Owner 输入不便 → 一键确认/拒绝（非三方辩论 120s）；微信消息延迟（秒级）→ 证据门控异步，不阻塞主 Loop；Owner 睡觉时 Butler 空闲 → 不触发混沌演练 `[G-10]`。

---

## 十二、配置与可观测性

### 12.1 配置：单一 Schema 替代 200+ 环境变量

```typescript
// config/schema.ts
import { Schema } from "@effect/schema"

export const ConfigSchema = Schema.struct({
  llm: Schema.struct({
    primary: Schema.string,
    fallback: Schema.string,
    apiKey: Schema.string,
  }),
  db: Schema.struct({
    url: Schema.string,
    poolSize: Schema.number.pipe(Schema.positive()),
  }),
  wechat: Schema.struct({
    appId: Schema.string,
    appSecret: Schema.string,
    ownerId: Schema.string,
  }),
  guards: Schema.struct({
    ownerOfflineThresholdMs: Schema.number.default(5 * 60 * 1000),
    chaosEnabled: Schema.boolean.default(false),  // [G-10] 默认关闭
    chaosCron: Schema.string.default("0 3 1 * *"),
    humanSigSecret: Schema.string,
  }),
  loop: Schema.struct({
    maxIterations: Schema.number.default(50),
    timeoutMs: Schema.number.default(10 * 60 * 1000),
  }),
})

export type ConfigShape = Schema.Schema.To<typeof ConfigSchema>
```

### 12.2 配置优先级

```
命令行参数 > 环境变量 > .env 文件 > 默认值
```

### 12.3 三层观测

| 层 | 内容 | 工具 |
|----|------|------|
| Metrics | QPS、延迟、错误率、守卫拦截率 `[G-*]` | Prometheus |
| Tracing | Effect.withSpan 自动埋点 `[OPT-17]` | OpenTelemetry |
| Logging | 结构化 JSON 日志 | Pino |

```typescript
// 守卫指标 [G-*]
export const guardMetrics = {
  guardBlocked: (g: G1|G2|G3|G4|G5|G6|G7|G8|G9|G10) => 
    counter("guard_blocked_total", { guard: g }),
  ownerOfflineQueueSize: () => gauge("owner_offline_queue_size"),
  chaosDrillResult: (scenario: string, ok: boolean) => 
    counter("chaos_drill_result_total", { scenario, ok: ok ? "1" : "0" }),
}
```

### 12.4 健康检查

```typescript
// apps/api/health.ts
export const healthCheck = Effect.gen(function* () {
  const db = yield* getDb()
  const llm = yield* LLMService
  return {
    db: yield* db.execute("SELECT 1").then(() => "ok").catch(() => "fail"),
    llm: yield* llm.complete([]).then(() => "ok").catch(() => "fail"),
    timestamp: Date.now(),
  }
})
```

### 12.5 HMAC 密钥管理 `[G-4]`

`[G-4]` ACP HUMAN 签名校验依赖 HMAC-SHA256 共享密钥，需在 Butler 和 Owner 微信端同步：

1. **密钥生成**：`openssl rand -hex 32` → 存入 `.env`（`GUARDS_HUMAN_SIG_SECRET`）
2. **分发**：Owner 在微信中首次配置时，通过加密通道发送密钥（一次性配置）
3. **存储**：仅存于环境变量，不写入文件或数据库
4. **轮换**：支持双密钥过渡期——新密钥 + 旧密钥同时验证 24 小时，之后废弃旧密钥
5. **泄漏应对**：立即轮换密钥，旧密钥签名的 pending 请求全部失效，要求 Owner 重新签名

```typescript
// config/schema.ts 补充
guards: Schema.struct({
  // ...
  humanSigSecret: Schema.string,                              // [G-4] 禁止硬编码
  humanSigSecretPrevious: Schema.optional(Schema.string),     // 轮换过渡期旧密钥
})
```

---

## 十三、测试策略

### 13.1 测试金字塔

```
        /\
       /  \     E2E（10%）：微信端到端
      /----\
     /      \   集成（20%）：application + 真 DB
    /--------\
   /          \ 单元（70%）：domain 纯函数
  /____________\
```

### 13.2 domain/ 测试：纯函数 + 代数定律

```typescript
// domain/guards/guards.test.ts（节选）
describe("verifyChain [G-5]", () => {
  it("完整链路 → completeness=1", () => {
    const spec = { mainFile: "a.tsx", expectedLinks: ["a.test.tsx", "a.css"] }
    expect(verifyChain(spec, ["a.tsx", "a.test.tsx", "a.css"]).completeness).toBe(1)
  })
  it("缺失文件 → 列出 missing", () => {
    const r = verifyChain({ mainFile: "a.tsx", expectedLinks: ["a.test.tsx", "a.css"] }, ["a.tsx", "a.test.tsx"])
    expect(r.completeness).toBeCloseTo(0.5); expect(r.missing).toEqual(["a.css"])
  })
})
// 代数定律：transition(s, NoOp) === s（fc.assert + fc.property）
```

### 13.3 application/ 测试：Mock Layer

```typescript
describe("runLoop [G-1] 证据门控", () => {
  it("无 evidenceFiles → MissingEvidence", async () => {
    const mockGuard = Layer.succeed(GuardService, {
      issueReceipt: () => Effect.succeed({ evidenceFiles: [] } as IntentReceipt), /* ... */
    })
    const exit = await pipe(runLoop({ conversationId: "t", userMessage: "do" }),
      Effect.provide(mockGuard), Effect.runPromiseExit)
    expect(Exit.isFailure(exit)).toBe(true)
  })
})
```

### 13.4 infrastructure/ 测试：真实 DB

```typescript
describe("GuardServiceLive [G-2] 承重代码", () => {
  it("承重路径 → require-owner-approval", async () => {
    const db = await createTestDb()
    await db.insert(loadBearingMarks).values({
      path: "butler/core/agent_loop/loop.py", reason: "核心循环",
      markedBy: "owner", ownerApproved: true, createdAt: new Date(), updatedAt: new Date(),
    })
    const result = await pipe(
      Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.checkLoadBearing("butler/core/agent_loop/loop.py", "write")
      }),
      Effect.provide(GuardServiceLive, TestDbLayer(db)), Effect.runPromise)
    expect(result.allowed).toBe(false)
  })
})
```

### 13.5 守卫测试矩阵

| GUARD | 测试场景 | 预期 |
|-------|---------|------|
| G-1 | delegate-task 无 evidenceFiles | fail with MissingEvidence |
| G-2 | 写 butler/core/agent_loop/loop.py | require-owner-approval |
| G-3 | Owner 离线 30 min + 写动作 | deny with OwnerOffline |
| G-4 | HMAC 签名错误 | fail with InvalidHumanSig |
| G-5 | 链路缺失 a.test.tsx | fail with ChainIncomplete |
| G-6 | LOC < 50 + isGenerated | Fast |
| G-7 | author == reviewer | fail with RoleConflict |
| G-8 | Retry 2 次失败 + Fallback 成功 | success |
| G-9 | 归档 anti-pattern | 文件写入 .butler/anti-patterns/ |
| G-10 | 每月 1 号 3 点 cron 触发 | chaosDrillResult 指标 +1 |

### 13.6 守卫测试（Guard Tests）`[NEW-OPT-21]`

**模式来源**：OpenHands + oh-my-openagent（78 项目调查 §4.1）。用 TS compiler API 扫描源码，强制架构约束——不是测功能，而是测"架构规则是否被违反"。

```typescript
// tests/guard/no-direct-fetch.test.ts
// 强制所有 API 调用必须走类型化客户端，禁止直接 fetch("/api/...")
describe("架构守卫：禁止裸 fetch", () => {
  it("所有 HTTP 调用必须经过 gateway 客户端", () => {
    const tsFiles = glob.sync("apps/**/*.ts", { ignore: "**/*.test.ts" })
    for (const file of tsFiles) {
      const source = readFileSync(file, "utf-8")
      // 检查是否直接使用了 fetch/axios
      expect(source).not.toMatch(/fetch\(['"]\/api\//)
    }
  })
})

// tests/guard/import-cycles.test.ts
// madge 检测循环依赖 [NEW-OPT-22]
describe("元审计：循环依赖", () => {
  it("零循环依赖", async () => {
    const result = await madge("packages/")
    expect(result.circular().length).toBe(0)
  })
})
```

### 13.7 元审计测试 + Floor Model `[NEW-OPT-22]` `[NEW-OPT-30]`

**模式来源**：oh-my-openagent（元审计）+ CodeGraph（Floor Model）。元审计测试测"测试本身是否被正确维护"；Floor Model 保证改动能在更弱模型上泛化。

```typescript
// tests/meta/mock-restore-audit.test.ts
// 检查所有 vi.mock(...) 是否在 afterEach 中 restore
describe("元审计：mock 恢复", () => {
  it("所有 mock 调用都有对应 restore", () => {
    // TS compiler API 扫描测试文件，检查 mock/restore 配对
  })
})

// Floor Model 策略：PR 必须在 Sonnet（floor model）上 land
// 如果 Sonnet 上都不行，说明改动让模型更弱了
// 配置：tests/floor-model-baseline.json 记录 Sonnet 基线
```

> **Eval 三层框架**（借鉴 agent-skills）：Tier 1 确定性测试（CI 每次跑）、Tier 2 集成测试（PR 触发）、Tier 3 headless Agent 评估（发版前跑，用 Sonnet 作为 floor model）。

---

## 十四、防错机制（10 条 GUARD）

### 14.1 机制总览

| 优先级 | ID | 机制 | 替代原哪些 | 章节定位 |
|--------|----|------|-----------|---------|
| P0 | G-1 | IntentReceipt（精简：intent + evidenceFiles + author） | 原 GUARD-1,3,6 | §3.5, §6.8, §8.1 |
| P0 | G-2 | 承重代码防护（.butler/load-bearing.json） | 原 GUARD-10 | §6.6, §6.8, §9.7 |
| P0 | G-3 | Owner 离线策略（默认拒绝写 / 队列等待） | 新增 | §11.3, §9.7 |
| P0 | G-4 | ACP HUMAN 签名校验 | 原 GUARD-27 | §9.7 |
| P1 | G-5 | 多文件链路校验（linkedFiles） | 原 GUARD-9 | §6.8, §9.7 |
| P1 | G-6 | 2 级验证（Fast / Standard）替代 4 级 | 原 GUARD-12 | §6.8, §8.1 |
| P1 | G-7 | 角色分离（AI Agent A ≠ Agent B 或 Owner） | 原 GUARD-2 | §6.7, §8.1 |
| P2 | G-8 | 3 层自愈（Retry / Fallback / OwnerNotify）替代 7 层 | 原 GUARD-5 | §6.8, §9.7 |
| P2 | G-9 | 反模式归档（Owner 手动触发，非自动） | 原 GUARD-16 | §9.7 |
| P2 | G-10 | 按需混沌演练（每月 1 次，非每天） | 原 GUARD-23 | §9.7 |

### 14.2 与 5 类 AI 失败模式的覆盖矩阵

| AI 失败模式 | 防御 GUARD |
|------------|-----------|
| ① AI 虚假完成 | G-1（IntentReceipt）+ G-6（验证级别）+ G-7（角色分离） |
| ② Owner 离线策略 | G-3（离线策略矩阵） |
| ③ 多文件漏改 | G-5（链路校验）+ G-6（Standard 验证） |
| ④ AI 伪造 Owner 确认 | G-4（HUMAN 签名）+ G-7（角色分离） |
| ⑤ 误删承重代码 | G-2（承重防护）+ G-4（Owner 签名） |

### 14.3 验证级别决策（2 级替代 4 级）`[G-6]`

| 级别 | 触发条件 | 验证方式 |
|------|---------|---------|
| Fast | augment 工具 + LOC < 50 | 仅 G-1 签发 + G-5 链路 |
| Standard | 其他所有写动作 | + G-7 角色分离 + Owner/AI persona 审查 |

> **精简说明**：原 4 级（Fast/Standard/Strict/Debate）→ 2 级。删除 Strict（合并入 Standard）和 Debate（Owner 微信一键确认即可，不需要 120s 三方辩论）。

### 14.4 3 层自愈（替代 7 层）`[G-8]`

| 层 | 触发 | 行为 |
|----|------|------|
| L1 Retry | 瞬时错误（网络、超时） | 指数退避重试 2 次 |
| L2 Fallback | Retry 失败或不可恢复 | 切换备用 provider/工具 |
| L3 OwnerNotify | Fallback 失败 | 微信通知 Owner 介入 |

> **精简说明**：原 7 层（Retry/Fallback/Compensate/CircuitBreak/Quarantine/Arbiter/OwnerNotify）→ 3 层。删除 Compensate（单人场景不需要事务补偿）、CircuitBreak（单实例不需要熔断）、Quarantine/Arbiter（合并入 OwnerNotify）。

### 14.5 混沌演练（按需，非每天）`[G-10]`

```typescript
// infrastructure/guards/chaos-scenarios.ts
export const chaosScenarios = [
  { name: "fake-completion",     inject: () => injectFakeEmptyReceipt(),      expect: "G-1 拦截 MissingEvidence" },
  { name: "owner-offline-write", inject: () => simulateOwnerOffline(3.6e6),   expect: "G-3 拒绝写动作" },
  { name: "multi-file-miss",     inject: () => injectPartialEvidenceFiles(),  expect: "G-5 拦截 ChainIncomplete" },
  { name: "fake-owner-sig",      inject: () => injectInvalidHumanSig(),       expect: "G-4 拦截 InvalidHumanSig" },
  { name: "load-bearing-delete", inject: () => attemptDeleteLoadBearing(),    expect: "G-2 拒绝 + 通知 Owner" },
]
```

**调度**：默认每月 1 号 3:00 触发（Owner 睡眠时段不影响业务）。Owner 通过微信手动触发可立即执行。

> **精简说明**：原 `[GUARD-31]` 自适应采样（cpuLoad/ioWait）已删除——Butler 单实例无集群负载自适应需求。

### 14.6 反模式归档（Owner 手动触发）`[G-9]`

```typescript
// 流程：Owner 微信发送 "归档反模式 <pattern>"
// → GuardService.archiveAntiPattern(pattern, evidence)
// → 写入 .butler/anti-patterns/<pattern>-<timestamp>.json
// → 下次契约加载时人工 review 是否加入 .cursorrules
```

> **精简说明**：原 `[GUARD-16]` 反模式自动提案（AI 自动检测 + 提案 + 加入规则）→ 改为 Owner 手动触发。AI 不能自动修改 .cursorrules（防止 AI 自我解除保护）。

### 14.7 LOC 奖惩（精简）`[G-9 配套]`

```typescript
// 仅"新增 > 预算 3x → WARN"，不引入多档奖惩
export function checkLocBudget(actual: number, budget: number): "ok" | "warn" {
  return actual > budget * 3 ? "warn" : "ok"
}
```

> **精简说明**：原 `[GUARD-24]` LOC 奖惩因子（5 档：under/within/over/much-over/abuse）→ 单条规则。

---

## 十五、迁移与实施路线图

### 15.1 总体策略：绞杀者模式（Strangler Fig）

```
v4 Python ──┬──[Phase 0]──> 准备期（环境 + Effect-TS 学习）
            ├──[Phase 1]──> v5 POC（核心域 + 最小 Loop）
            ├──[Phase 2]──> 完整域 + 基础守卫（G-1/G-3）
            ├──[Phase 3]──> 基础设施 + 网关 + 完整守卫（G-2/G-4/G-5/G-6/G-7/G-8）
            └──[Phase 4]──> 迁移 + 收尾（G-9/G-10 + 混沌演练）
```

### 15.2 反腐层（Anti-Corruption Layer）

```typescript
// infrastructure/acl/v4-adapter.ts
export class V4Adapter extends Context.Tag("V4Adapter")<
  V4Adapter,
  {
    readonly importV4Conversation: (id: string) => Effect.Effect<Conversation, LoopError>
    readonly exportV5Receipt: (r: IntentReceipt) => Effect.Effect<void, never>
  }
>() {}
```

### 15.3 双写一致性：Outbox Pattern

v5 写事件 + 写 Outbox 在同一事务（见 §10.3），Outbox Publisher 异步消费 → 微信/HTTP。

### 15.4 数据迁移

```typescript
// infrastructure/migration/v4-to-v5.ts
export const migrateV4ToV5 = Effect.gen(function* () {
  yield* migrateConversations()       // v4 conversations → v5 ConversationStarted + MessageAdded 事件
  yield* migrateBlackboardCards()     // v4 .blackboard/shifts → v5 IntentReceipts（authorAgent="v4-legacy"）
})
```

### 15.5 影子模式验证

```typescript
// 影子模式：v4 仍处理真实流量，v5 接收副本执行并比对结果（不影响业务）
export const shadowMode = Effect.gen(function* () {
  const v4 = yield* V4Adapter
  yield* v4.subscribeMessages().pipe(
    Stream.runForEach(msg => Effect.gen(function* () {
      const v5Result = yield* Effect.either(runLoop({ conversationId: msg.convId, userMessage: msg.content }))
      yield* logShadowResult(msg, v5Result)
    }))
  )
})
```

### 15.6 Phase 详表（24 周）

| Phase | 周次 | 目标 | 关键产出 |
|-------|------|------|---------|
| **Phase 0** | **W1–2** | **准备期** | Monorepo 骨架 + docker-compose + Effect-TS 关键 POC + CI 骨架 |
| Phase 1 | W3–8 | 核心域 + 最小 Loop | 对话域 ADT、Effect Loop（Mock LLM）、单测 ≥ 90% |
| Phase 2 | W9–14 | 完整域 + 基础守卫 | 全部 6 域 + **G-1（IntentReceipt）+ G-3（Owner 离线）** |
| Phase 3 | W15–20 | 基础设施 + 网关 + 完整守卫 | Drizzle + EventStore + WeChat Gateway + **G-2/G-4/G-5/G-6/G-7/G-8** 全集成 |
| Phase 4 | W21–24 | 迁移 + 收尾 | 绞杀者迁移 + 影子模式 + **G-9/G-10** + 混沌演练首次通过 |

> **缓冲说明**：每 Phase 末尾含 1 周缓冲（W8/W14/W20/W24），用于修复 bug、补充测试、代码审查。如超时可按降级策略裁减 P3 功能（OPT-16/17/18）或延迟 P2 守卫（G-9/G-10）。

### 15.7 POC 验收标准

| 标准 | 验证方式 |
|------|---------|
| 对话 Loop 跑通 | 给定任务 → 产出 IntentReceipt |
| 纯函数测试覆盖 | domain/ ≥ 90% |
| Effect Layer 注入 | 9 个 Tag 全部可替换 |
| 启动内存 | < 6MB |
| 防错骨架 | Phase 1.5 10 条 GUARD 全部 stub + 测试通过 |

### 15.9 性能基准

| 指标 | v4 基线 | v5 目标 |
|------|---------|---------|
| 初始内存 | 15MB | < 6MB |
| 单轮 LLM 调用 | 2.3s | < 2s |
| 事件追加延迟 | N/A | < 5ms |
| 守卫检查延迟 | N/A | < 50ms（Fast）/ < 500ms（Standard） |

### 15.9 首次混沌演练验收（Phase 4）

- 5 个 chaosScenarios 全部触发
- 每个场景对应 GUARD 拦截率 100%
- Owner 微信收到通知 + 1 键确认
- 演练日志归档到 `.butler/anti-patterns/`

---

## 十六、不采纳设计 + 附录

### 16.1 不采纳设计（含精简说明）

**通用不采纳**：

| 设计 | 不采纳原因 |
|------|-----------|
| Scala + ZIO | 单语言团队成本；Effect-TS 已足够 |
| 全量 Event Sourcing（无 snapshot） | 长会话回放慢；用 `[OPT-12]` Hybrid Store |
| WASM 沙箱 | 部署复杂；dev_engine 用进程级隔离即可 |
| Python 子进程网关 | v5 完全重写，不需要兼容 v4 网关 |
| 类继承体系 | 与 FC/IS 冲突；用 Effect Layer + 函数组合 |
| 隐式异常（throw） | 违反"错误是值"原则；用 `Effect.fail` + ADT |
| RxJS | Effect Stream 已是超集 |
| 手动 Reader Monad DI | Effect Layer 原生支持 |

**V14.1 过度工程机制（22 条）→ 不采纳/精简**（详见 §16.4 附录 C）：

| 精简方向 | 代表性机制 |
|---------|-----------|
| 合并入精简 GUARD | 7 层自愈→3 层（G-8）；4 级验证→2 级（G-6）；4 个独立 Tag→单 GuardService；Arbiter→G-7；WriteThenNotify→Outbox |
| 降级为标准 lint | TypeEscapeLinter 钻石级；PrivacySanitizer + DynamicFence → PII 脱敏 lint |
| 复用现有方案 | PageRank 独立实现→复用 `[OPT-14]`；ShadowEngine 独立采样→复用 `[OPT-12]` Snapshot；FailurePathArchive 自动提案→Owner 手动（G-9） |
| 后置 P3 | DeltaChannel V2 双计数器；DependencyWatcher + LockfileDriftChecker |
| 删除（Butler 单人/单实例） | WorkspaceRaceDetector；ChaosService 自适应采样；reviewerPool 多人；三方辩论 120s → Owner 一键确认；5 张新表→2 张 |
| 结构精简 | 28 章 2914 行 → 17 章 ~2050 行（含 78 项目分析新增 18 条 OPT） |

### 16.2 附录 A：优化建议索引（18 条原 OPT + 18 条新增）

**原 OPT-1~OPT-18**（来自 2026-07-30 版，基于 10 个高星项目）：

| # | 优先级 | 标题 | 章节定位 | 来源 |
|---|-------|------|---------|------|
| OPT-1 | P0 | Channel 抽象 | §6.4 | LangGraph |
| OPT-2 | P0 | interrupt/resume + Command API | §7.2 | LangGraph |
| OPT-3 | P0 | Spec SDD 四制品 | §6.5 | spec-kit |
| OPT-4 | P0 | 变更类型分类 | §6.4 | OpenSpec |
| OPT-5 | P1 | 工具 Schema 自动转 JSON Schema | §6.2 | OpenCode |
| OPT-6 | P1 | MCP 动态发现 + 缓存失效 | §9.3 | Cline |
| OPT-7 | P1 | Dream 两阶段记忆巩固 | §6.3, §8.3 | nanobot |
| OPT-8 | P1 | 双策略压缩 | §6.1 | Cline |
| OPT-9 | P1 | 轻量 EventBus | §11.1 | nanobot |
| OPT-10 | P2 | AgentPersona 三元组 | §6.1 | crewAI |
| OPT-11 | P2 | Send API 并行委派 | §6.4, §8.2 | LangGraph |
| OPT-12 | P2 | DeltaChannel 增量检查点 | §9.4 | LangGraph |
| OPT-13 | P2 | RelativeIndenter + 多策略 patch | §9.5 | aider |
| OPT-14 | P2 | PageRank repo-map | §9.6 | aider |
| OPT-15 | P2 | 工具自动发现 | §6.2 | nanobot |
| OPT-16 | P3 | ContextGraph 有向图 | §6.1 | Gemini-CLI |
| OPT-17 | P3 | Effect.withSpan 自动埋点 | §12.3 | LangGraph |
| OPT-18 | P3 | ArtifactGraph 文件存在性推断 | （后置） | OpenSpec |

**新增 OPT-19~OPT-36**（来自 78 项目深度分析，2026-07-31）：

| # | 优先级 | 标题 | 章节定位 | 来源 |
|---|-------|------|---------|------|
| OPT-19 | P0 | Scope 边界四栏表（Reads/Writes/Executes/Off-limits） | §3.6 | GitNexus（78 项目调查 §2.3） |
| OPT-20 | P0 | 历史反模式注册表（L-001 格式 + fix commit） | §3.7 | lobehub（78 项目调查 §2.4） |
| OPT-21 | P0 | 守卫测试（TS compiler API 扫描架构约束） | §13.6 | OpenHands（78 项目调查 §4.1） |
| OPT-22 | P0 | 元审计测试（mock 恢复 + 循环依赖检测） | §13.7 | oh-my-openagent（78 项目调查 §4.2） |
| OPT-23 | P0 | Harness 模板系统（按模型自动切换 system prompt） | §7.6 | OpenInterpreter（Harness 仿真） |
| OPT-24 | P0 | 七级决策阶梯（YAGNI→代码库→标准库→最小实现） | §3.8 | Ponytail（The Ladder） |
| OPT-25 | P0 | 三层 Skill 架构（Commands→Personas→Skills） | （后置 §8.4） | agent-skills（三层组合） |
| OPT-26 | P1 | 双层进程架构（Gateway 轻量父进程 + Worker 子进程） | （后置 §11.4） | Gemini-CLI（Rearch 模式） |
| OPT-27 | P1 | 事件驱动调度器（五阶段：摄入→验证→确认→执行→终结） | §7.7 | Gemini-CLI（Scheduler） |
| OPT-28 | P1 | 并行工具执行（只读工具默认并行，写工具顺序） | §7.7 | Gemini-CLI（并行调度） |
| OPT-29 | P1 | Token 预算硬限制（超限自动暂停，Owner 确认恢复） | （后置 §8.1） | Paperclip（Budget） |
| OPT-30 | P1 | Floor Model 策略（Sonnet 作为 floor model 保证泛化） | §13.7 | CodeGraph（回归基线） |
| OPT-31 | P1 | Branded Type 路径（ReadPath/WritePath 防止误用） | （后置 §6.2） | oh-my-claudecode（78 项目调查 §3.5） |
| OPT-32 | P2 | 四种交互模式（Plan/Ask/Auto-Review/Full Access） | （后置 §8.1） | CodeWhale（权限分层） |
| OPT-33 | P2 | LSP 集成（文件写入后自动触发诊断） | （后置 §9.5） | CodeWhale（LSP 诊断） |
| OPT-34 | P2 | 智能模型路由（Haiku/Sonnet/Opus 按任务类型分配） | （后置 §9.1） | OMC（泳道路由） |
| OPT-35 | P2 | description 驱动路由（Skill description 作为唯一路由接口） | （后置 §8.4） | agent-skills（语义路由） |
| OPT-36 | P2 | Parity 追踪（v4→v5 迁移 parity 文档 + 自动化校验） | （后置 §15.1） | Claw Code（PARITY.md） |

### 16.3 附录 B：10 条 GUARD 机制索引

| ID | 优先级 | 机制 | 章节定位 | 替代原 GUARD |
|----|--------|------|---------|-------------|
| G-1 | P0 | IntentReceipt（精简） | §3.5, §6.8, §8.1 | 原 GUARD-1,3,6 |
| G-2 | P0 | 承重代码防护 | §6.6, §6.8, §9.7 | 原 GUARD-10 |
| G-3 | P0 | Owner 离线策略 | §11.3, §9.7 | 新增 |
| G-4 | P0 | ACP HUMAN 签名校验 | §9.7 | 原 GUARD-27 |
| G-5 | P1 | 多文件链路校验 | §6.8, §9.7 | 原 GUARD-9 |
| G-6 | P1 | 2 级验证（Fast/Standard） | §6.8, §8.1, §14.4 | 原 GUARD-12 |
| G-7 | P1 | 角色分离 | §6.7, §8.1, §14.2 | 原 GUARD-2 |
| G-8 | P2 | 3 层自愈 | §6.8, §9.7, §14.5 | 原 GUARD-5 |
| G-9 | P2 | 反模式归档（Owner 手动） | §9.7, §14.7 | 原 GUARD-16 |
| G-10 | P2 | 按需混沌演练（每月 1 次） | §9.7, §14.6 | 原 GUARD-23 |

### 16.4 附录 C：删除的 22 条过度工程机制

原 V14.1 的 32 条机制中，**保留 10 条 → G-1..G-10**，删除/合并 22 条：

- **降级为字段**（无独立 GUARD ID）：原 4/7/8/17/21/22 → 字段保留在对应 ADT
- **合并入精简 GUARD**：原 5→G-8、9→G-5、11→LoopError、12→G-6、13→G-8、14→GuardService.loadContract、16→G-9、18→G-7、20→Outbox、24→G-9 配套、32→G-9
- **降级为标准 lint**：原 25（TypeEscapeLinter）、30（PrivacySanitizer）
- **删除（Butler 单人/单实例场景不需要）**：原 15（安全分级演化，与 .cursorrules 重复）、26（ArchitectureGuardAnalyzer，同上）、28（WorkspaceRaceDetector）、31（自适应采样，固定每月 1 次）
- **后置 P3**：原 19（DeltaChannel V2 双计数器）、29（DependencyWatcher + LockfileDriftChecker）

### 16.5 附录 D：数据库 schema 一览（4 张表）

| 表 | 来源 | 字段数 | 说明 |
|----|------|--------|------|
| `events` | 新增（事件溯源） | 6 | EventStore 写模型 + 审计 |
| `outbox` | 新增（双写一致性） | 6 | Outbox Pattern，出站消息 |
| `intent_receipts` | 新增（G-1） | 10 | 含 guardFindings JSON |
| `load_bearing_marks` | 新增（G-2） | 7 | 含 ownerApproved 标记 |

> **精简说明**：原方案 6 张表（含 conversations/messages CQRS 读模型）→ 4 张。读模型直接从事件流投影，查询性能不足时按需引入 PostgreSQL MATERIALIZED VIEW。

### 16.6 附录 E：应用启动顺序

```typescript
// apps/api/main.ts
Effect.gen(function* () {
  const config = yield* loadConfig()                              // 1. 加载配置
  yield* initDbPool(config.db)                                     // 2. 数据库连接池
  const guard = yield* GuardService                                // 3. 加载契约（AGENTS.md + .cursorrules）
  const contract = yield* guard.loadContract()
  yield* OutboxPublisher.pipe(Effect.forkDaemon)                  // 4. Outbox Publisher（双写一致性）
  yield* startGateway.pipe(Effect.forkDaemon)                      // 5. 微信网关
  yield* OwnerPresenceMonitor.pipe(Effect.forkDaemon)              // 6. Owner 在线监听 [G-3]
  if (config.guards.chaosEnabled)                                  // 7. 混沌调度器（可选，默认关闭）[G-10]
    yield* guard.scheduleChaos("all", config.guards.chaosCron).pipe(Effect.forkDaemon)
  yield* Effect.never                                              // 8. 主进程阻塞
}).pipe(Effect.provide(ProductionLayer), Effect.runPromise)
```

### 16.7 参考文档

**Butler v5 文档族**：[`butler-v5-complete-design`](butler-v5-complete-design-2026-07-30.md)（上一版 SSOT，18 条 OPT 来源）、[`functional-architecture`](butler-v5-functional-architecture-2026-07-30.md)（原始主架构）、[`optimization-from-projects`](butler-v5-optimization-from-projects-2026-07-30.md)（18 条 OPT 详述）、[`migration-plan`](functional-architecture-migration-plan-2026-07-30.md)（迁移主方案）、[`strangler-fig`](strangler-fig-migration-guide-2026-07-30.md)（绞杀者模式）。

**防错机制参考**：[`reference/代码医生方案参考.md`](../../reference/代码医生方案参考.md)（Code Doctor V14.1，2546 行，仅取适配部分）。

**Butler v4 参考文档**：[`v4-architecture`](../architecture/v4-architecture.md)、[`v4-layer-model`](../architecture/v4-layer-model.md)、[`config/reference`](../config/reference.md)。

**审查报告**：[`butler-v5-final-review-and-plan-2026-07-30.md`](butler-v5-final-review-and-plan-2026-07-30.md)（DeepSeek 独立审查 + 最终开发计划，与本 SSOT 互补）。

---

## 十七、开发环境与 CI/CD

### 17.1 本地开发环境

```bash
# 1. 启动 PostgreSQL
docker-compose up -d postgres

# 2. 安装依赖
pnpm install

# 3. 初始化数据库
pnpm db:migrate
pnpm db:seed    # 加载 .butler/load-bearing.json 初始数据

# 4. 启动开发服务器（hot-reload）
pnpm dev

# 5. 运行测试
pnpm test              # 全部测试
pnpm test:watch        # watch 模式
pnpm test:coverage     # 覆盖率报告

# 6. 类型检查
pnpm typecheck
```

**docker-compose.yml** 核心服务：

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: butler_v5
      POSTGRES_USER: butler
      POSTGRES_PASSWORD: butler_dev
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  wechat-mock:  # 微信 webhook 模拟器（开发用）
    image: node:20-alpine
    # 模拟微信消息收发，用于本地集成测试
```

### 17.2 CI/CD Pipeline（GitHub Actions）

```yaml
# .github/workflows/ci.yml
name: Butler v5 CI
on: [push, pull_request]

jobs:
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
      - run: pnpm install
      - run: pnpm lint
      - run: pnpm typecheck

  test:
    needs: lint-and-typecheck
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_DB: butler_test, POSTGRES_USER: test, POSTGRES_PASSWORD: test }
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
      - run: pnpm install
      - run: pnpm db:migrate
      - run: pnpm test -- --coverage
      - run: pnpm test:integration  # 真 PostgreSQL 集成测试

  guard-gates:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm test:guards       # 10 条 GUARD 集成测试
      - run: pnpm test:chaos        # 5 个混沌场景测试
```

### 17.3 本地调试技巧

```typescript
// 使用 Mock LLM 快速调试 Loop（不消耗 API 额度）
const TestLayer = Layer.mergeAll(
  LLMServiceLiveMock,  // 返回预设脚本，不调用真 API
  DrizzleEventStoreTest,  // 内存 SQLite（测试用）
  ToolExecutorLive,
  // ... 其他 Layer
)
```

---

**文档状态**：终极设计方案 SSOT（精简版），覆盖架构/领域/端口/基础设施/迁移/路线图/验证 + **10 条精简 GUARD 机制**（覆盖 5 类 AI 失败模式）+ **开发环境与 CI/CD**。

**下次更新触发**：POC 验证完成（Phase 1）、首次混沌演练通过（Phase 4）、实施后回顾防错机制拦截率调整守卫阈值。
