# 绞杀者模式深度指南：FC/IS 逐步替换 Service 层

> **配套文档**：[functional-architecture-migration-plan-2026-07-30.md](functional-architecture-migration-plan-2026-07-30.md)

---

## 一、绞杀者模式核心机制

### 1.1 三阶段演进模型

```
阶段 1: 并行运行期
┌─────────────────────────────────────────────────┐
│  客户端请求                                      │
│       │                                          │
│       ▼                                          │
│  ┌───────────┐                                  │
│  │ 路由分发器 │ ←── 根据配置决定走老/新/影子模式    │
│  └─────┬─────┘                                  │
│        │                                        │
│   ┌────┴────┐                                   │
│   │         │                                   │
│   ▼         ▼                                   │
│ ┌─────┐  ┌─────┐                                │
│ │老   │  │新   │  影子模式：两者都跑，比对结果       │
│ │Python│  │TS   │  只返回老系统结果，新系统仅记录     │
│ └─────┘  └─────┘                                │
│   │         │                                   │
│   └────┬────┘                                   │
│        │                                        │
│        ▼                                        │
│   客户端响应（老系统结果）                         │
└─────────────────────────────────────────────────┘

阶段 2: 渐进切换期
┌─────────────────────────────────────────────────┐
│  客户端请求                                      │
│       │                                          │
│       ▼                                          │
│  ┌───────────┐                                  │
│  │ 路由分发器 │ ←── 按百分比灰度切换               │
│  └─────┬─────┘                                  │
│        │                                        │
│   ┌────┴────┐                                   │
│   │         │                                   │
│   ▼         ▼                                   │
│ ┌─────┐  ┌─────┐                                │
│ │老   │  │新   │  流量分配：如 10% 新 / 90% 老    │
│ │Python│  │TS   │  返回各自系统结果               │
│ └─────┘  └─────┘                                │
└─────────────────────────────────────────────────┘

阶段 3: 完全切换期
┌─────────────────────────────────────────────────┐
│  客户端请求                                      │
│       │                                          │
│       ▼                                          │
│  ┌───────────┐                                  │
│  │ 路由分发器 │ ←── 全部流量导向新系统             │
│  └─────┬─────┘                                  │
│        │                                        │
│        ▼                                        │
│     ┌─────┐                                     │
│     │新   │  100% 流量走 TS 新系统                 │
│     │TS   │  老系统仅作为 fallback                 │
│     └─────┘                                     │
└─────────────────────────────────────────────────┘
```

### 1.2 五个关键步骤

```
1. 识别 Service 边界 ──────── 确定绞杀单元
2. 建立反腐败层（ACL） ──────── 隔离新老系统
3. 影子模式验证 ──────────── 并行运行 + 结果比对
4. 渐进流量切换 ──────────── 1% → 100% 灰度
5. 切断老系统 ──────────── 移除老代码
```

---

## 二、识别 Butler v4 的 Service 边界

### 2.1 绞杀单元划分原则

| 原则 | 说明 | Butler 示例 |
|------|------|-------------|
| **依赖方向单向** | 该模块不依赖更底层的未迁移模块 | `ops/` 只依赖 `contracts/` 接口 |
| **接口稳定** | 通过 Port 接口暴露，无内部泄露 | `contracts/` 定义的 Port 接口 |
| **可独立部署** | 该模块可独立运行和测试 | `ops/` 可独立启动验证 |
| **风险可控** | 失败不影响核心业务 | `ops/` 是只读观测层 |

### 2.2 Butler 的绞杀单元识别

```
优先级排序（从低风险到高风险）：

1. 🔵 ops/         — 观测层，只读，边界清晰
2. 🔵 permissions/ — 纯函数，无副作用，最易迁移
3. 🟡 memory/      — 读写混合，需要双写策略
4. 🟡 tools/      — 副作用密集，需要适配器
5. 🟡 transport/  — HTTP 客户端，Effect-TS 原生支持
6. 🔴 core/        — 核心逻辑，最高风险
7. 🔴 gateway/     — 微信协议，需要重写
```

### 2.3 Service 边界识别清单

以 `ops/` 为例，识别其 Service 边界：

```python
# contracts/eval_ports.py (已存在的 Port 接口)
class EvalPort(Protocol):
    def submit_eval(self, result: EvalResult) -> Awaitable[None]: ...
    def query_eval(self, session_key: str) -> Awaitable[EvalSummary]: ...

# ops/eval_feedback.py (实现 Port 的 Service)
class EvalFeedbackService:
    def submit_eval(self, result: EvalResult):
        # 副作用：写数据库、推通知
        ...

# 在 TS 中对应的 Service 边界
// src/core/eval/eval-service.ts
export interface EvalService {
  readonly submit: (result: EvalResult) => Effect.Effect<void, EvalError>
  readonly query: (sessionKey: string) => Effect.Effect<EvalSummary, EvalError>
}
```

---

## 三、反腐败层（ACL）设计

### 3.1 ACL 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Anti-Corruption Layer                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  协议适配层                                          │   │
│  │  - Python Port ↔ TS Effect 接口映射                  │   │
│  │  - 数据格式转换（Pydantic ↔ Zod）                     │   │
│  │  - 错误码映射                                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  通信层                                              │   │
│  │  - gRPC/HTTP 双向通信                                │   │
│  │  - 序列化/反序列化                                    │   │
│  │  - 连接池管理                                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  缓存层                                              │   │
│  │  - 接口结果缓存                                      │   │
│  │  - 一致性校验                                        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 ACL 实现示例

#### Python 端

```python
# contracts/eval_ports.py
# 这是稳定的 Port 接口，不会改变

from typing import Protocol, Awaitable

class EvalQueryPort(Protocol):
    def query_eval(self, session_key: str) -> Awaitable[dict]: ...

class EvalCommandPort(Protocol):
    def submit_eval(self, result: dict) -> Awaitable[None]: ...
```

```python
# gateway/eval_bridge.py
# ACL: Python 侧桥接实现

class ACLBridge:
    """反腐败层：确保 Python 老系统不受 TS 新系统实现细节影响"""
    
    def __init__(self, grpc_channel):
        self._channel = grpc_channel
    
    async def query_eval(self, session_key: str) -> dict:
        """将 Python Port 调用转换为 gRPC 调用"""
        request = QueryEvalRequest(session_key=session_key)
        response = await self._channel.QueryEval(request)
        return self._convert_response(response)
    
    async def submit_eval(self, result: dict) -> None:
        request = SubmitEvalRequest(result=json.dumps(result))
        await self._channel.SubmitEval(request)
    
    def _convert_response(self, response) -> dict:
        """gRPC 响应 → Python dict"""
        return {
            "session_key": response.session_key,
            "score": response.score,
            ...
        }
```

#### TypeScript 端

```typescript
// src/adapters/eval-bridge.ts
// ACL: TS 侧桥接实现

import { Effect, Layer, Context } from "effect"

// 稳定的 Port 接口（对应 Python contracts/eval_ports.py）
export interface EvalQueryPort {
  readonly query: (sessionKey: string) => Effect.Effect<EvalSummary, EvalError>
}

export interface EvalCommandPort {
  readonly submit: (result: EvalResult) => Effect.Effect<void, EvalError>
}

// gRPC 客户端
const GrpcClient = Context.Tag<GrpcClient>()

// ACL 实现
const makeEvalBridge = Effect.gen(function* (_) {
  const client = yield* _(GrpcClient)

  const query: EvalQueryPort["query"] = (sessionKey) =>
    Effect.tryPromise({
      try: () => client.QueryEval({ sessionKey }),
      catch: (e) => new EvalTransportError(String(e)),
    }).flatMap((response) =>
      Effect.try({
        try: () => parseEvalResponse(response),
        catch: (e) => new EvalParseError(String(e)),
      })
    )

  const submit: EvalCommandPort["submit"] = (result) =>
    Effect.tryPromise({
      try: () => client.SubmitEval({ result: JSON.stringify(result) }),
      catch: (e) => new EvalTransportError(String(e)),
    })

  return { query, submit }
})

// Layer 绑定
export const EvalBridgeLive = Layer.effect(
  EvalQueryPort,
  makeEvalBridge
).pipe(
  Layer.provide((port) => ({
    query: port.query,
  }))
)
```

### 3.3 数据格式转换

```
Python Pydantic          ←→  TypeScript Zod
───────────────────────────────────────────
class EvalResult(BaseModel):  ←→  const EvalResult = z.object({
    session_key: str             sessionKey: z.string(),
    score: float                 score: z.number(),
    confidence: float            confidence: z.number(),
    metrics: dict[str, Any]      metrics: z.record(z.string(), z.unknown()),
    timestamp: datetime          timestamp: z.string().datetime(),
})                              })

# ACL 转换逻辑
# Python → TS: snake_case → camelCase
# TS → Python: camelCase → snake_case
```

---

## 四、影子模式（Shadow Mode）实现

### 4.1 影子模式架构

```
                    ┌──────────────────────┐
                    │   请求入口           │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   主路径（老系统）     │ ← 返回结果给用户
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   影子路径（新系统）   │ ← 结果仅用于比对
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   结果比对器          │ ← 记录差异
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   差异日志           │ ← 供人工审计
                    └──────────────────────┘
```

### 4.2 影子模式实现

#### Python 端路由分发器

```python
# gateway/shadow_router.py

class ShadowRouter:
    """影子模式路由器"""
    
    def __init__(self, python_service, ts_acl, shadow_config):
        self._python = python_service
        self._ts_acl = ts_acl
        self._config = shadow_config  # { mode: "shadow" | "cutover", ratio: 0.1 }
        self._diff_logger = DiffLogger()
    
    async def route(self, request):
        """根据配置路由请求"""
        
        if self._config.mode == "shadow":
            # 影子模式：两个都跑
            python_result = await self._python.handle(request)
            
            # 异步调用 TS 新系统
            ts_result = await self._run_shadow(request)
            
            # 比对结果
            self._diff_logger.compare(python_result, ts_result, request)
            
            # 返回老系统结果
            return python_result
        
        elif self._config.mode == "cutover":
            # 渐进切换模式
            if random.random() < self._config.ratio:
                return await self._ts_acl.handle(request)
            else:
                return await self._python.handle(request)
    
    async def _run_shadow(self, request):
        """影子调用：不影响主流程"""
        try:
            return await self._ts_acl.handle(request)
        except Exception as e:
            # 影子失败不影响主流程
            self._diff_logger.log_error(request, e)
            return None
```

#### TypeScript 端结果比对器

```typescript
// src/ops/diff-comparator.ts

interface DiffResult {
  readonly timestamp: number
  readonly requestId: string
  readonly differences: string[]
  readonly severity: "info" | "warning" | "error"
}

const compareResults = (
  pythonResult: unknown,
  tsResult: unknown,
  requestId: string
): Effect.Effect<DiffResult, never> =>
  Effect.gen(function* (_) {
    const differences: string[] = []

    // 字段级比对
    const pythonObj = normalizeKeys(pythonResult, "snake_case")
    const tsObj = normalizeKeys(tsResult, "camelCase")

    for (const key of Object.keys(pythonObj)) {
      const pyVal = pythonObj[key]
      const tsVal = tsObj[key]

      if (pyVal !== tsVal) {
        differences.push(`Field "${key}": ${String(pyVal)} vs ${String(tsVal)}`)
      }
    }

    // 统计严重程度
    const severity =
      differences.length === 0
        ? "info"
        : differences.length < 3
          ? "warning"
          : "error"

    return {
      timestamp: Date.now(),
      requestId,
      differences,
      severity,
    }
  })
```

---

## 五、流量切换与回滚

### 5.1 渐进切换策略

```
时间线（每阶段观察 24 小时）：

Day 1-3:   影子模式（100% 老系统 + 100% 影子新系统）
           ↓ 确认无严重差异
Day 4-6:   切换 1% 流量到新系统
           ↓ 观察无异常
Day 7-9:   切换 5% 流量
           ↓ 观察无异常
Day 10-12: 切换 20% 流量
           ↓ 观察无异常
Day 13-15: 切换 50% 流量
           ↓ 持续稳定
Day 16+:   切换 100% 流量
           ↓ 稳定运行 7 天
Day 23+:   移除老系统代码
```

### 5.2 自动回滚触发条件

```python
# gateway/rollback_manager.py

class RollbackManager:
    """自动回滚管理器"""
    
    ROLLBACK_CONDITIONS = [
        # 错误率超过阈值
        {"metric": "error_rate", "threshold": 0.05, "action": "rollback"},
        
        # P99 延迟超过阈值
        {"metric": "p99_latency_ms", "threshold": 2000, "action": "rollback"},
        
        # 差异率超过阈值
        {"metric": "diff_rate", "threshold": 0.01, "action": "alert"},
        
        # 严重错误（如数据库连接失败）
        {"metric": "critical_errors", "threshold": 1, "action": "rollback"},
    ]
    
    def check_and_rollback(self, metrics):
        """检查指标并触发回滚"""
        for condition in self.ROLLBACK_CONDITIONS:
            if metrics[condition["metric"]] > condition["threshold"]:
                if condition["action"] == "rollback":
                    self._execute_rollback()
                elif condition["action"] == "alert":
                    self._send_alert(condition, metrics)
    
    def _execute_rollback(self):
        """执行回滚到 Python 老系统"""
        self.router.set_mode("cutover", ratio=0.0)
        self._notify_team("ROLLBACK: 已切回 Python 老系统")
```

### 5.3 回滚检查清单

| 检查项 | 通过条件 |
|--------|----------|
| 错误率 < 5% | TS 新系统错误率不超过 Python 的 120% |
| P99 延迟 < 2s | TS 新系统延迟不超过 Python 的 150% |
| 差异率 < 1% | 影子模式下结果差异 < 1% |
| 无数据不一致 | 双写数据偏差 < 0.01% |
| 无内存泄漏 | 24 小时运行内存稳定 |

---

## 六、Butler 各层迁移难度评估

### 6.1 各层迁移详情

| 层 | 模块 | 文件数 | 迁移难度 | 核心挑战 | 预计时间 |
|----|------|--------|----------|----------|----------|
| **L9** | ops/ | 138 | ⭐⭐ 低 | 数据格式转换 | 3 周 |
| **L7** | permissions/ | 12 | ⭐ 极低 | 无 | 1 周 |
| **L5** | memory/ | 141 | ⭐⭐⭐ 中 | 向量存储迁移、双写 | 4 周 |
| **L4** | tools/ | 119 | ⭐⭐⭐ 中 | 工具 Schema 迁移、Zod | 4 周 |
| **L6** | transport/ | 39 | ⭐⭐ 中 | HTTP 客户端迁移 | 2 周 |
| **L4** | mcp/ | 44 | ⭐⭐ 中 | MCP 协议适配 | 2 周 |
| **L4** | skills/ | 28 | ⭐⭐ 中 | Skill 格式迁移 | 2 周 |
| **L2** | orchestrator/ | 10 | ⭐⭐⭐ 中 | 编排逻辑重写 | 2 周 |
| **L3** | core/ | 299 | ⭐⭐⭐⭐⭐ 高 | Agent Loop 重构、状态管理 | 6 周 |
| **L1** | gateway/ | 197 | ⭐⭐⭐⭐ 高 | 微信协议重写 | 4 周 |

### 6.2 推荐迁移顺序（实际路径）

```
第 1 步:  [POC] 最小 Agent Loop 验证（2 周）
  │
第 2 步:  Phase 0 - 基础设施 + ACL（2 周）
  │
第 3 步:  Phase 1 - 低风险模块
  │       ├── permissions/（1 周）
  │       └── ops/（3 周）
  │
第 4 步:  Phase 2 - 中等风险模块
  │       ├── transport/（2 周）
  │       ├── mcp/（2 周）
  │       └── skills/（2 周）
  │
第 5 步:  Phase 3 - 核心业务模块
  │       ├── memory/（4 周）
  │       └── tools/（4 周）
  │
第 6 步:  Phase 4 - 最高风险模块
  │       ├── orchestrator/（2 周）
  │       ├── gateway/（4 周）
  │       └── core/ agent_loop/（6 周）
  │
第 7 步:  收尾 - 文档 + 测试 + Python 退役（2 周）
```

---

## 七、FC/IS 模式在各层的应用

### 7.1 命令式外壳（Shell）包含什么

| 层 | 外壳职责 | 技术 |
|----|----------|------|
| **Gateway Shell** | HTTP/微信协议解析、请求路由 | Hono + Effect.run |
| **Database Shell** | Drizzle ORM 操作、事务管理 | Drizzle + PostgreSQL |
| **LLM Shell** | HTTP 调用、流式处理、重试 | Effect + fetch |
| **Cache Shell** | Redis 读写、缓存策略 | Effect + ioredis |

### 7.2 函数式核心（Core）包含什么

| 层 | 核心职责 | 技术 |
|----|----------|------|
| **Agent Loop** | 对话状态机、轮次迭代 | Effect.gen + ADT |
| **Context Pipeline** | 上下文压缩、修复、裁剪 | pipe + Either |
| **Tool Registry** | 工具注册、查找、调度 | Effect + Map + Reader |
| **Memory** | 记忆检索、排序、注入 | Effect + Option + State |
| **Permissions** | 权限判断、规则校验 | 纯函数 + ADT |
| **Events** | 事件发布、订阅、回放 | Effect Stream + Sink |

### 7.3 FC/IS 数据流示例

```typescript
// === 函数式核心（纯计算） ===

// ADT 建模对话状态
type DialogState =
  | { readonly _tag: "Init" }
  | { readonly _tag: "Processing"; readonly turn: number }
  | { readonly _tag: "WaitingToolResult"; readonly pendingTools: string[] }
  | { readonly _tag: "Completed"; readonly response: string }
  | { readonly _tag: "Error"; readonly reason: DialogError }

// 纯函数：状态转换
const transition = (
  state: DialogState,
  event: DialogEvent
): DialogState => {
  switch (state._tag) {
    case "Init":
      return event._tag === "UserMessage"
        ? { _tag: "Processing", turn: 1 }
        : state
    case "Processing":
      if (event._tag === "LLMResponse") {
        return event.needsMoreTools
          ? { _tag: "WaitingToolResult", pendingTools: event.tools }
          : { _tag: "Completed", response: event.response }
      }
      return state
    // ... 其他转换
  }
}

// === 命令式外壳（副作用） ===

const runDialog = (userMessage: string) =>
  Effect.gen(function* (_) {
    // 外壳：初始化
    let state: DialogState = { _tag: "Init" }
    let event: DialogEvent = { _tag: "UserMessage", content: userMessage }

    // 核心：纯函数状态机
    while (state._tag !== "Completed" && state._tag !== "Error") {
      state = transition(state, event)

      switch (state._tag) {
        case "Processing": {
          // 外壳：调用 LLM（副作用）
          const llmResult = yield* _(llmClient.complete(messages))
          event = { _tag: "LLMResponse", ...llmResult }
          break
        }
        case "WaitingToolResult": {
          // 外壳：执行工具（副作用）
          const toolResults = yield* _(toolExecutor.execute(state.pendingTools))
          event = { _tag: "ToolResults", results: toolResults }
          break
        }
      }
    }

    return state
  })
```

---

## 八、成功标准与度量

### 8.1 各阶段度量

| 阶段 | 核心度量 | 目标值 |
|------|----------|--------|
| **POC** | Agent Loop 延迟 | < Python 版 150% |
| **Phase 0** | ACL 通信成功率 | > 99.9% |
| **Phase 1** | ops 影子差异率 | < 0.1% |
| **Phase 2** | 记忆双写一致性 | > 99.99% |
| **Phase 3** | 工具执行准确率 | 100% |
| **Phase 4** | 对话质量评分 | ≥ Python 版 |

### 8.2 整体迁移成功标志

1. ✅ TS 新系统承载 100% 流量
2. ✅ Python 老系统代码完全移除
3. ✅ 所有测试在 TS 中重新建立并通过
4. ✅ 性能指标优于或不劣于 Python 版
5. ✅ 团队掌握 Effect-TS 开发模式
6. ✅ 新功能优先在 TS 中开发
