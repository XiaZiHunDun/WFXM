# Butler v5 — DeepSeek 审查报告 + 最终开发计划

> **日期**：2026-07-30
> **审查人**：DeepSeek 模型（替代 GLM）
> **审查对象**：[`butler-v5-final-design-2026-07-30.md`](butler-v5-final-design-2026-07-30.md)（1797 行，SSOT 精简版）
> **文档定位**：基于第一性原理的独立审查，输出最终优化方案 + 可执行开发计划

---

## 目录

1. [审查总评](#一审查总评)
2. [12 个优化点详析](#二12-个优化点详析)
3. [最终优化方案](#三最终优化方案)
4. [最终开发计划（24 周）](#四最终开发计划24-周)
5. [风险评估与缓解](#五风险评估与缓解)
6. [成功标准](#六成功标准)
7. [附录：变更清单](#七附录变更清单)

---

## 一、审查总评

### 1.1 整体评价

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构方向 | ★★★★★ | FC/IS + Effect-TS + ADT 方向正确，是 v4 散乱 Python 的最佳解药 |
| 第一性原理匹配 | ★★★★☆ | 5 类 AI 失败模式定位精准，但基础设施选型偏离单人 Owner 场景 |
| 防错机制 | ★★★★☆ | 10 条 GUARD 精简得当，但 Phase 1.5 过早（应在核心 Loop 稳定后） |
| 开发计划可行性 | ★★★☆☆ | 18 周过于乐观，缺少 Effect-TS 学习曲线、调试、集成测试缓冲 |
| 基础设施务实性 | ★★★☆☆ | Redis Stream、PageRank repo-map、全量 CQRS 对单人项目过度 |
| 文档完整性 | ★★★☆☆ | 缺少风险评估、CI/CD、开发环境、回滚策略、认证模型 |

**总评**：方案骨架优秀，但**执行层面需要大幅务实化**。以下 12 个优化点按影响力排序。

### 1.2 审查方法论

本次审查基于 Butler 项目的**第一性原理**（见 §2.3 原文）：
- 单人 Owner + 多 AI Agent 的微信编码管家
- Owner 离线是常态，微信消息有延迟
- 不是企业级多开发者协作系统

**判定标准**：任何增加基础设施复杂度、运维负担、或学习曲线的设计，必须能**直接服务于 5 类 AI 失败模式的防御**，否则视为过度工程。

---

## 二、12 个优化点详析

### 优化点 1（P0）：时间线从 18 周调整为 24 周

**问题**：18 周（4.5 个月）对以下工作量过于乐观：
- 学习 Effect-TS（Layer/Fiber/Stream/Schedule 需要 2-3 周上手）
- 18 条 OPT + 10 条 GUARD + CQRS + Event Sourcing + 微信网关 + 迁移 + 影子模式
- 单人开发，无并行团队

**修正**：调整为 **24 周（6 个月）**，增加 Phase 0（准备期）+ 每 Phase 末尾 1 周缓冲。

### 优化点 2（P0）：Redis Stream → PostgreSQL LISTEN/NOTIFY

**问题**：原文 §4.1 选型 Redis Stream 7.x 作为消息队列，但 Butler 是单实例部署：
- Redis 增加运维负担（额外进程、内存管理、持久化配置）
- 单实例场景下 PostgreSQL 的 `LISTEN/NOTIFY` + `pg_notify()` 完全可以替代
- EventBus 的 `subscribe()` 本身就是 in-process 的，不需要外部 MQ

**修正**：删除 Redis Stream 依赖，出站消息用 PostgreSQL `LISTEN/NOTIFY` 或 in-process EventBus。开发环境无需启动 Redis。

### 优化点 3（P1）：CQRS 读写分离 → 事件日志 + 投影

**问题**：原文 §10.2 的 CQRS 方案（conversations/messages 读表 + events 写表）对单人项目过度：
- 维护两套 schema 和投影器增加复杂度
- 单人 Owner 场景的查询并发极低（每秒个位数），不需要读写分离的性能优势
- 投影器 `ConversationProjector` 增加了故障点

**修正**：保留 Event Sourcing 的事件日志（审计价值），但读模型简化为**直接从事件流投影**，不维护独立的 `conversations`/`messages` 读表。仅在需要查询优化时（如按日期范围查历史对话）才引入物化视图。

```typescript
// 简化：直接从事件投影，不维护独立读表
export function loadConversation(events: readonly ConversationEvent[]): ConversationState {
  return events.reduce(transition, { _tag: "Idle" })
}
// 仅在查询性能不足时引入物化视图（PostgreSQL MATERIALIZED VIEW）
```

### 优化点 4（P1）：PageRank repo-map → 简单重要性评分

**问题**：原文 §9.6 的 PageRank repo-map 需要：
- 解析所有文件的 import 图
- 运行 PageRank 算法
- 维护计算结果（文件变更时需重新计算）

对于单人 Owner 项目，文件数量通常在 200-500 个，不需要 PageRank 级别的排序。

**修正**：简化为**基于目录 + 配置的简单评分**：

```typescript
// 简单重要性评分（替代 PageRank）
export function scoreFileImportance(path: string, marks: readonly LoadBearingMark[]): number {
  let score = 0
  if (path.startsWith("butler/core/")) score += 5            // 核心模块
  if (path.startsWith("butler/gateway/")) score += 3         // 网关层
  if (marks.some(m => m.path === path)) score += 80         // 承重标记
  if (path.endsWith(".test.ts") || path.endsWith("_test.py")) score = 0  // 测试文件低优先级
  return score
}
```

### 优化点 5（P1）：纯函数中的副作用 bug

**问题**：原文 §6.1 `transition` 函数中：

```typescript
case "OwnerInputReceived":
  return state._tag === "AwaitingOwnerInput"
    ? { _tag: "Running", loopId: state.loopId ?? crypto.randomUUID() }  // BUG!
    : state
```

`crypto.randomUUID()` 是副作用（随机数生成），在纯函数中调用违反了 FC/IS 原则，导致函数不可测试、不可预测。

**修正**：将 `loopId` 生成移到 `application/` 层，`transition` 只接受已有 `loopId`：

```typescript
// domain/ - 纯函数
export function transition(state: ConversationState, event: ConversationEvent): ConversationState {
  switch (event._tag) {
    case "OwnerInputReceived":
      return state._tag === "AwaitingOwnerInput" && event.loopId
        ? { _tag: "Running", loopId: event.loopId }
        : state
    // ...
  }
}

// application/ - 副作用
const loopId = crypto.randomUUID()
const newState = transition(state, { _tag: "OwnerInputReceived", loopId })
```

### 优化点 6（P1）：硬编码路径 → 配置驱动

**问题**：原文 §6.8 `scoreDeletionRisk` 中硬编码了 `"loop.py"` 和 `"agent_loop/loop.py"`：

```typescript
if (path.endsWith("loop.py") || path.endsWith("agent_loop/loop.py")) {
  score += 50; reasons.push("涉及核心循环")
}
```

这不可维护——如果核心文件改名或被重构，这段逻辑就会失效。

**修正**：删除硬编码路径，完全依赖 `LoadBearingMark` 配置（`.butler/load-bearing.json`），由 Owner 人工维护。`scoreDeletionRisk` 只检查 `marks` 参数：

```typescript
export function scoreDeletionRisk(path: string, marks: readonly LoadBearingMark[], locRemoved: number): DeletionRisk {
  const matched = marks.filter(m => m.path === path)
  let score = matched.length > 0 ? 80 : 0
  const reasons = matched.map(m => m.reason)
  if (locRemoved > 100) { score += 20; reasons.push(`删除行数 ${locRemoved} > 100`) }
  return { score: Math.min(score, 100), reasons }
}
```

### 优化点 7（P2）：Phase 1.5 防错骨架过早 → 融入 Phase 2

**问题**：原文 §15.6 在 W5-6 就构建完整的 10 条 GUARD 骨架，但此时核心 Loop 尚未稳定（Phase 1 刚完成 POC）。守卫是用来保护核心 Loop 的，如果 Loop 本身还在变化，守卫的接口和逻辑会频繁改动。

**修正**：删除 Phase 1.5，将防错机制**渐进式融入各 Phase**：
- Phase 1（W1-4）：核心 Loop POC，不涉及守卫
- Phase 2（W5-9）：完整域 + 先实现 G-1（IntentReceipt）+ G-3（Owner 离线），因为它们是 Loop 运行的基础
- Phase 3（W10-16）：基础设施 + 网关 + G-2/G-4/G-5/G-6/G-7/G-8 全集成
- Phase 4（W17-22）：迁移 + G-9/G-10 + 混沌演练

### 优化点 8（P2）：`checkOwnerOnline` 类型不安全

**问题**：原文 §9.7 中 `checkOwnerOnline` 接受 `action: string`，然后用 `isWriteAction(action)` 判断：

```typescript
checkOwnerOnline: (action) => Effect.sync(() => {
  if (!isWriteAction(action)) return { decision: "allow", ... }
  // ...
})
```

`isWriteAction` 需要解析字符串，容易出错。

**修正**：使用类型化参数：

```typescript
checkOwnerOnline: (action: { toolId: string; category: "read" | "write" | "execute" | "delegate" }) =>
  Effect.sync(() => {
    if (action.category === "read") return { decision: "allow", reason: "读动作放行" } as const
    // ...
  })
```

### 优化点 9（P2）：`heal` 方法中的类型问题

**问题**：原文 §9.7 `GuardService.heal` 返回类型是 `Effect.Effect<A, E | domain.LoopError>`，但最后 `Effect.catchAll` 内部又 `Effect.fail(e)`，意味着它永远不会成功返回——这实际上是一个"通知后仍失败"的语义，但类型签名暗示可能成功。

**修正**：明确 `heal` 的语义是"尽力修复，失败后通知 Owner 并返回原始错误"：

```typescript
heal: <A, E>(effect: Effect.Effect<A, E>, options: {
  maxRetry: number; fallback?: () => Effect.Effect<A, E>
}) => effect.pipe(
  Effect.retry({ times: options.maxRetry }),
  Effect.catchAll(e => options.fallback ? options.fallback() : Effect.fail(e)),
  Effect.tapError(e => Effect.gen(function* () {
    const wx = yield* WeChatGateway
    yield* wx.send(OWNER_WXID, `[自愈失败] ${String(e)}，需介入`)
  }))
)
```

用 `Effect.tapError` 替代 `Effect.catchAll`，语义更清晰：通知 Owner 但不改变错误流。

### 优化点 10（P2）：6 张数据库表 → 4 张

**问题**：原文 §16.5 的 6 张表（conversations、messages、intent_receipts、load_bearing_marks、events、outbox）中，conversations 和 messages 是 CQRS 读模型，如果按优化点 3 简化，可以删除。

**修正**：保留 4 张表：
- `events`（Event Sourcing 事件流）
- `outbox`（出站消息，双写一致性）
- `intent_receipts`（G-1 证据锚定）
- `load_bearing_marks`（G-2 承重防护）

### 优化点 11（P3）：缺少开发环境与 CI/CD 设计

**问题**：原文没有开发环境搭建指南、CI/CD pipeline 设计、本地调试方法。

**修正**：在最终方案中增加：
- **开发环境**：`docker-compose up` 启动 PostgreSQL + 微信 webhook 模拟器
- **CI/CD**：GitHub Actions 运行 lint + typecheck + 单元测试 + 集成测试（真 PostgreSQL）
- **本地调试**：`pnpm dev` 启动 hot-reload 开发服务器，`pnpm test:watch` 持续运行测试

### 优化点 12（P3）：HMAC 密钥管理未说明

**问题**：原文 §9.7 的 `HUMAN_SECRET` 用于 HMAC-SHA256 签名，但未说明：
- 密钥如何生成和分发（Owner 手机需要同一密钥）
- 密钥如何存储（环境变量？文件？）
- 密钥轮换策略

**修正**：在 §12 配置章节增加：
- 密钥生成：`openssl rand -hex 32` → 存入 `.env`（`GUARDS_HUMAN_SIG_SECRET`）
- 分发：Owner 在微信中首次配置时，通过加密通道发送密钥
- 轮换：支持双密钥过渡期（新密钥 + 旧密钥同时验证 24 小时）

---

## 三、最终优化方案

基于以上 12 个优化点，对原方案进行以下调整：

### 3.1 技术选型调整

| 原选型 | 调整后 | 理由 |
|--------|--------|------|
| Redis Stream 7.x | ~~删除~~ → PostgreSQL LISTEN/NOTIFY | 单实例不需要外部 MQ（优化点 2） |
| CQRS 读写分离（6 张表） | 事件日志 + 按需投影（4 张表） | 单人场景不需要读写分离（优化点 3、10） |
| PageRank repo-map | 简单目录+配置评分 | 200-500 文件不需要 PageRank（优化点 4） |
| 18 周 | 24 周（6 个月） | 增加学习曲线 + 缓冲（优化点 1） |
| Phase 1.5 防错骨架 | 融入 Phase 2/3 | 核心 Loop 稳定后再加守卫（优化点 7） |

### 3.2 架构调整一览

| 原设计 | 调整 | 影响 |
|--------|------|------|
| `transition` 含 `crypto.randomUUID()` | 移除副作用（优化点 5） | domain/ 保持纯函数 |
| `scoreDeletionRisk` 硬编码路径 | 改为配置驱动（优化点 6） | 可维护性提升 |
| `checkOwnerOnline(action: string)` | 类型化参数（优化点 8） | 类型安全 |
| `heal` 用 `catchAll` 后 `fail` | 改为 `tapError`（优化点 9） | 语义正确 |
| 缺 CI/CD / 开发环境 | 增加 §17（优化点 11） | 可执行性 |
| 缺 HMAC 密钥管理 | 增加 §12.4（优化点 12） | 可部署性 |

### 3.3 数据库最终 schema（4 张表）

```sql
-- 事件流（Event Sourcing 写模型 + 审计）
CREATE TABLE events (
  id TEXT PRIMARY KEY,
  stream_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_events_stream ON events(stream_id, version);

-- 出站消息（Outbox Pattern，双写一致性）
CREATE TABLE outbox (
  id TEXT PRIMARY KEY,
  aggregate_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload JSONB NOT NULL,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_outbox_pending ON outbox(published_at) WHERE published_at IS NULL;

-- 证据锚定（G-1）
CREATE TABLE intent_receipts (
  id TEXT PRIMARY KEY,
  intent TEXT NOT NULL,
  evidence_files JSONB NOT NULL,
  loc_delta JSONB NOT NULL,
  chain_completeness INTEGER NOT NULL DEFAULT 1,
  guard_findings JSONB NOT NULL DEFAULT '[]',
  author_agent TEXT NOT NULL,
  reviewer_agent TEXT,
  owner_approval_sig TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 承重代码标记（G-2）
CREATE TABLE load_bearing_marks (
  path TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  marked_by TEXT NOT NULL,
  owner_approved BOOLEAN NOT NULL DEFAULT FALSE,
  alternatives JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 四、最终开发计划（24 周）

### 4.1 总体策略

绞杀者模式（Strangler Fig），渐进替换 v4。v4 继续运行，v5 通过影子模式逐步接管流量。

### 4.2 Phase 0：准备期（W1-2）

**目标**：环境搭建 + Effect-TS 学习 + 关键风险验证

| 周次 | 任务 | 产出 |
|------|------|------|
| W1 | 搭建 Monorepo（pnpm + Turborepo + tsconfig） | `butler-v5/` 骨架 |
| W1 | docker-compose 开发环境（PostgreSQL + 微信模拟器） | `docker-compose.yml` |
| W1 | Effect-TS 学习：Layer / Fiber / Stream / Schedule 核心 API | 学习笔记 + 小 demo |
| W2 | 关键风险 POC：Effect Layer DI 替代 9 个单例 | `infrastructure/layers.ts` 可运行 |
| W2 | 关键风险 POC：Effect.retry + Schedule 替代 Python 重试逻辑 | 对比测试 |
| W2 | GitHub Actions CI 骨架（lint + typecheck + test） | `.github/workflows/ci.yml` |

**验收**：`pnpm test` 通过（空测试骨架）、`pnpm typecheck` 通过、CI 绿灯。

### 4.3 Phase 1：核心域 + 最小可行 Loop（W3-8）

**目标**：对话域 ADT + Effect Loop 可运行，不含守卫

| 周次 | 任务 | 产出 |
|------|------|------|
| W3-4 | domain/conversation/：Message / ConversationState / ConversationEvent ADT | 纯函数 + 单测 ≥ 90% |
| W4-5 | domain/errors.ts：LoopError ADT（不含 GuardRejected） | 错误 ADT |
| W5-6 | ports/：LLMService / EventStoreService / ToolExecutor Tag | 接口定义 |
| W6-7 | application/run-loop/：最小 Loop（LLM → ToolCall → LLM 循环） | 可运行 Loop |
| W7-8 | infrastructure/：LLMServiceLive（Mock LLM）+ DrizzleEventStoreLive | 集成测试 |
| W8 | 缓冲周：修复 bug、补充测试、代码审查 | |

**验收**：给定 Mock LLM 脚本，Loop 从用户消息 → 工具调用 → 产出对话结果。启动内存 < 8MB。domain/ 测试覆盖率 ≥ 90%。

### 4.4 Phase 2：完整域 + 基础守卫（W9-14）

**目标**：全部 6 个域 + G-1（IntentReceipt）+ G-3（Owner 离线策略）

| 周次 | 任务 | 产出 |
|------|------|------|
| W9-10 | domain/tools/ + domain/memory/ + domain/workflows/ + domain/projects/ + domain/permissions/ | 5 个域 ADT + 纯函数 |
| W10-11 | ports/：MemoryService / WorkflowService / ProjectService / WeChatGateway Tag | 接口定义 |
| W11-12 | application/：run-workflow / dream / delegate-task 用例 | 用例编排 |
| W12-13 | **G-1 实现**：IntentReceipt ADT + issueReceipt + intent_receipts 表 | 证据门控可用 |
| W13-14 | **G-3 实现**：OwnerPresenceMonitor + checkOwnerOnline + 离线策略矩阵 | Owner 离线防护可用 |
| W14 | 缓冲周 | |

**验收**：delegate-task 无 evidenceFiles → MissingEvidence 错误。Owner 离线 30 分钟 + 写动作 → deny。全部域测试通过。

### 4.5 Phase 3：基础设施 + 网关 + 完整守卫（W15-20）

**目标**：Drizzle + EventStore + WeChat Gateway + G-2/G-4/G-5/G-6/G-7/G-8

| 周次 | 任务 | 产出 |
|------|------|------|
| W15-16 | infrastructure/persistence/：Drizzle schema + EventStore + Outbox | 数据持久化 |
| W16-17 | apps/wechat-gateway/：入站 EventBus + 出站 Outbox Publisher | 微信网关 |
| W17-18 | **G-2 + G-4**：checkLoadBearing + verifyHumanSig + load_bearing_marks 表 | 承重防护 + 签名校验 |
| W18-19 | **G-5 + G-6 + G-7**：verifyChain + pickVerification + checkRoleSeparation | 链路校验 + 验证级别 + 角色分离 |
| W19-20 | **G-8**：heal（Retry → Fallback → OwnerNotify）集成到 LLMServiceLive + 工具执行 | 3 层自愈 |
| W20 | 缓冲周 | |

**验收**：微信消息 → Loop → 工具执行 → IntentReceipt 全链路。10 条 GUARD 中 8 条（G-1..G-8）通过集成测试。

### 4.6 Phase 4：迁移 + 收尾（W21-24）

**目标**：绞杀者迁移 + 影子模式 + G-9 + G-10 + 混沌演练

| 周次 | 任务 | 产出 |
|------|------|------|
| W21 | 数据迁移：v4 conversations → v5 事件流（V4Adapter） | 迁移脚本 |
| W21 | 影子模式：v4 仍处理真实流量，v5 接收副本并比对结果 | 影子模式运行 |
| W22 | **G-9**：archiveAntiPattern + Owner 微信触发 | 反模式归档 |
| W22 | **G-10**：chaosScenarios + Schedule.cron 调度 | 混沌演练框架 |
| W23 | 首次混沌演练：5 个场景全部触发，GUARD 拦截率 100% | 演练报告 |
| W23-24 | 性能基准测试、文档完善、最终验收 | |
| W24 | 缓冲周：切流准备 | |

**验收**：影子模式运行 1 周无回归。5 个混沌场景全部拦截。Owner 微信收到通知并 1 键确认。性能基准达标。

### 4.7 开发计划总览

```
Week  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24
Phase 0  ██
Phase 1        ██ ██ ██ ██ ██ ██
Phase 2                       ██ ██ ██ ██ ██ ██
Phase 3                                      ██ ██ ██ ██ ██ ██
Phase 4                                                     ██ ██ ██ ██
Buffer                              ██                ██                ██
```

### 4.8 里程碑

| 里程碑 | 周次 | 验收标准 |
|--------|------|---------|
| M1: POC | W8 | Mock LLM 驱动 Loop 完成对话 |
| M2: 基础防错 | W14 | G-1 + G-3 通过集成测试 |
| M3: 完整防错 | W20 | G-1..G-8 通过集成测试 |
| M4: 生产就绪 | W24 | 影子模式 + 混沌演练 + 性能基准 |

---

## 五、风险评估与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Effect-TS 学习曲线陡峭 | 高 | 延迟 Phase 1-2 | Phase 0 专项学习 + 关键 API POC |
| Effect-TS 版本 breaking change | 中 | 编译失败 | 锁定版本 + Renovate 自动升级 PR |
| 微信 API 变更 | 中 | 网关不可用 | WeChatGateway 接口抽象 + Mock 测试 |
| v4 迁移数据丢失 | 低 | 历史对话丢失 | 影子模式先行验证 + 迁移脚本幂等 |
| PostgreSQL 性能不足 | 低 | 查询延迟 | 事件流按月分区 + 物化视图按需 |
| 单人开发瓶颈 | 高 | 延期 | 每 Phase 末尾 1 周缓冲 + 功能降级策略 |
| Owner 密钥泄露 | 低 | 签名伪造 | 环境变量存储 + 双密钥轮换 + 审计日志 |

### 功能降级策略

如果某 Phase 超时，可降级的功能（按优先级）：
1. **P3 后置**：OPT-16（ContextGraph）、OPT-17（withSpan）、OPT-18（ArtifactGraph）
2. **P2 可延迟**：G-9（反模式归档）、G-10（混沌演练）
3. **P1 可简化**：G-5（多文件链路校验简化为手动配置）、G-7（角色分离简化为 Owner 审查）

---

## 六、成功标准

### 6.1 功能验收

- [ ] 微信发送任务 → Loop 执行 → 工具调用 → IntentReceipt 产出
- [ ] Owner 离线 30 分钟 → 写动作被拒绝
- [ ] 修改承重代码 → 要求 HUMAN 签名
- [ ] 多文件链路缺失 → ChainIncomplete 拦截
- [ ] LLM 不可用 → 自动切换 Fallback provider
- [ ] 5 个混沌场景全部被对应 GUARD 拦截

### 6.2 质量验收

- [ ] domain/ 测试覆盖率 ≥ 90%
- [ ] 全部 10 条 GUARD 有集成测试
- [ ] 启动内存 < 8MB
- [ ] 单轮 LLM 调用延迟 < 2s（P50）
- [ ] 守卫检查延迟 < 50ms（Fast）/ < 500ms（Standard）
- [ ] TypeScript strict mode 通过
- [ ] CI 全绿（lint + typecheck + test）

### 6.3 运维验收

- [ ] docker-compose up 一键启动开发环境
- [ ] 健康检查端点（/health）返回 db/llm 状态
- [ ] 结构化日志输出（JSON 格式）
- [ ] 守卫拦截计数器（Prometheus metrics）

---

## 七、附录：变更清单

### 7.1 需要修改原文档的条目

| 原 § | 变更 | 理由 |
|------|------|------|
| §4.1 技术栈 | 删除 Redis Stream | 优化点 2 |
| §4.1 技术栈 | 运行时 Node.js 20 LTS → 备注 Bun 可选 | 性能差异不影响单人场景 |
| §6.1 transition | 移除 `crypto.randomUUID()` | 优化点 5 |
| §6.8 scoreDeletionRisk | 删除硬编码路径 | 优化点 6 |
| §7.3 GuardService.checkOwnerOnline | 参数类型化 | 优化点 8 |
| §9.6 PageRank | 改为简单评分 | 优化点 4 |
| §9.7 GuardService.heal | `catchAll` → `tapError` | 优化点 9 |
| §10.2 CQRS | 删除 conversations/messages 读表 | 优化点 3 |
| §15.6 Phase 详表 | 18 周 → 24 周，删除 Phase 1.5 | 优化点 1、7 |
| §16.5 数据库 schema | 6 张表 → 4 张表 | 优化点 10 |

### 7.2 需要新增的章节

| 新增 § | 内容 | 理由 |
|--------|------|------|
| §17 | 开发环境与 CI/CD | 优化点 11 |
| §12.4 | HMAC 密钥管理 | 优化点 12 |
| §5 风险评估 | 见本报告 §五 | 完整性 |
| §6 成功标准 | 见本报告 §六 | 可验收 |

### 7.3 建议保留不变的设计

以下设计经过审查确认合理，建议保留：

- **FC/IS 边界划分**（§3.2）：正确
- **10 条 GUARD 机制**（§14）：精简得当，覆盖 5 类失败模式
- **18 条 OPT 建议**（§16.2）：优先级合理，P3 后置策略正确
- **绞杀者迁移模式**（§15.1）：正确
- **Outbox Pattern**（§10.3）：正确
- **Effect-TS 技术选型**（§4.2）：正确
- **Event Sourcing 事件流**（§10.1）：审计价值高，保留
- **GuardService 单 Tag 合并**（§7.3）：正确
- **2 级验证替代 4 级**（§14.3）：正确
- **3 层自愈替代 7 层**（§14.5）：正确

---

**文档状态**：DeepSeek 独立审查报告 + 最终开发计划。与 [`butler-v5-final-design-2026-07-30.md`](butler-v5-final-design-2026-07-30.md) 互补——本报告侧重**执行可行性与务实优化**，原方案侧重**架构设计**。

**下一步**：按本报告 §七变更清单更新原文档，然后按 §四开发计划启动 Phase 0。