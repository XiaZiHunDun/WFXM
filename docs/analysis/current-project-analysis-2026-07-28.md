# Butler v4 当前项目方案分析

> **日期**：2026-07-28
> **目的**：为后续重构提供完整的现状分析与技术债务清单
> **分析范围**：代码结构、架构设计、技术栈、数据流、测试、可维护性

---

## 一、项目概览

### 1.1 项目定位

**Butler v4** 是一个**多项目微信 AI 管家系统**，采用**自建 Agent Loop** 架构。核心目标是：

- 通过微信（iLink Bot API）为用户提供 AI 管家服务
- 支持多项目隔离管理（每个项目独立的配置、记忆、工具集）
- 完全控制 Agent Loop（不依赖 Hermes AIAgent），实现深度可定制
- 提供从开发到运营的完整闭环（开发引擎、记忆系统、观测评估）

### 1.2 规模统计

| 维度 | 数量 | 说明 |
|------|------|------|
| Python 代码文件 | 1,490 | `butler/` 目录 |
| 代码总行数 | ~196,707 | 不含测试 |
| 测试文件 | 824 | `tests/` 目录 |
| 测试代码行数 | ~127,442 | |
| 测试用例数 | ~12,058 | 可收集用例（545 被 marker 排除）|
| 配置项 | 200+ `BUTLER_*` | 环境变量 + config.yaml |
| 文档 | 50+ 份 | 架构/指南/规划/配置参考 |

### 1.3 各层模块分布

| 层 | 模块 | 文件数 | 说明 |
|----|------|--------|------|
| L1 接入与交互 | `gateway/` | 197 | 微信网关、消息队列、平台适配 |
| L3 认知推理环 | `core/` | 299 | Agent Loop、上下文、工具、LLM、会话 |
| L4 工具与能力 | `tools/` | 119 | 11 内置工具 + 可选工具 |
| L5 记忆与知识 | `memory/` | 141 | 向量存储、语义索引、经验挖掘 |
| L9 观测与运营 | `ops/` | 138 | 评估、诊断、指标、报告 |
| L6 模型与协议 | `transport/` | 39 | 9 家 LLM 厂商协议适配 |
| L2 编排与控制 | `orchestrator/` | 10 | 系统提示、Skill 路由、工厂 |
| L4 MCP | `mcp/` | 44 | MCP 客户端/服务器、Schema 规范化 |
| L4 DevEngine | `dev_engine/` | 84 | 开发引擎、代码知识、验证 |
| L4 Skills | `skills/` | 28 | Skill 管理、融合、学习 |
| L2 Workflows | `workflows/` | 17 | DAG 工作流、运行器、验证 |
| L4 Runtime | `runtime/` | 35 | 运行时服务、委派、调度 |
| L7 Permissions | `permissions/` | 12 | 工具权限、人工门控 |
| 契约 | `contracts/` | 32 | Port 接口、Registry、事件 |
| 其他 | 9 个包 | ~145 | session, delegate, project, registry, cli, eval, experiments, report, hooks |

---

## 二、核心架构设计

### 2.1 九层参考模型

```
L1 接入与交互 ─── 微信网关 / CLI / main.py
     │
L2 编排与控制 ─── Orchestrator / Workflows / Runtime
     │
L3 认知推理环 ─── AgentLoop / ContextPipeline / ToolBatch / LLMRetry
     │              │          │          │
L4 工具与能力  L5 记忆与知识  L6 模型与协议
  Tools/MCP/    Memory/       Transport/
  Skills/       VectorDB/     Providers/
  DevEngine     SemanticIdx   LLMClient
     │              │          │
L7 策略与门控 ─── Permissions / HumanGate
     │
L8 可靠性与韧性 ─── Queue / Outbox / Failover / Retry
     │
L9 观测与运营 ─── Metrics / Eval / Health / Report
     │
─────────────── 横切：butler/contracts/ (Port + Registry) ───────────────
```

### 2.2 Agent Loop 架构（核心引擎）

Agent Loop 是整个系统的心脏，负责单轮对话的完整执行：

```
用户消息 → sanitize_surrogates
    │
    ▼
┌─ prepare 阶段 ──────────────────────────────────┐
│  ContextPipeline:                                │
│    1. tool_prune (分级 micro 剪枝)                │
│    2. compress_context (阈值门控压缩)              │
│    3. post_compact (锚点重注入)                    │
│    4. repair_message_sequence                    │
│    5. sanitize_api                               │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─ LLM 阶段 ─────────────────────────────────────┐
│  llm_retry + interruptible_client:               │
│    - 空内容重试                                   │
│    - schema 恢复                                 │
│    - 压缩回退                                    │
│    - Provider failover (9 家厂商)                  │
│    - 流式响应 (on_tool_call_ready 预取)           │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─ Tool 阶段 ─────────────────────────────────────┐
│  tool_batch + parallel_tools:                   │
│    - 工具调度 (registry envelope)                 │
│    - guardrails (循环检测/幂等分类)                │
│    - 并行执行 (precheck halt/interrupt)           │
│    - 结果 spill (大结果落盘)                       │
│    - read_state (写前校验 mtime)                  │
└─────────────────────────────────────────────────┘
    │
    ▼
  LoopResult (status + transition_reason + diagnostics)
```

### 2.3 设计模式总结

| 模式 | 应用位置 | 说明 |
|------|----------|------|
| **Port/Registry** | `contracts/` | 依赖倒置：核心层定义 Port 接口，外层实现 Registry |
| **Registry + Discovery** | `tools/registry.py` | 工具自注册、动态 schema 覆写、AST 发现 |
| **Pipeline** | `core/context_pipeline.py` | 上下文处理管线（可插拔阶段） |
| **Strategy** | `transport/fallback.py` | Provider 失败时的切换策略链 |
| **Guard/Policy** | `tools/guardrails.py` | 工具循环检测与阻断（4 种算法）|
| **Singleton + Lazy** | `utilities/singleton.py` | 线程安全单例（双重检查锁定） |
| **Event Sourcing** | `contracts/events.py` | 基于事件的会话状态变更记录 |
| **Module-level `__getattr__`** | `core/__init__.py` | 惰性导入，减少初始内存 |
| **Two-phase Loading** | `skills/progressive_disclosure.py` | 元数据发现 → 按需全量加载 |
| **Bridge + Adapter** | `gateway/platforms/wechat_ilink/` | 微信 iLink 协议适配 |

---

## 三、技术栈

### 3.1 核心依赖

| 类别 | 库 | 版本 | 用途 |
|------|-----|------|------|
| LLM API | `openai`, `anthropic` | 2.21+/0.39+ | 多厂商 LLM 调用 |
| HTTP | `httpx[socks]` | 0.28+ | 同步/异步 HTTP 客户端 |
| 数据验证 | `pydantic` | 2.12+ | 运行时类型校验 |
| CLI | `rich`, `prompt_toolkit` | 14+/3.0+ | 终端交互与渲染 |
| 重试 | `tenacity` | 9.1+ | 指数退避重试 |
| 配置 | `python-dotenv`, `pyyaml` | 1.2+/6.0+ | .env / YAML 配置 |
| JWT | `PyJWT[crypto]` | 2.12+ | 微信 token 认证 |
| 向量 | `aiosqlite`, `chromadb` | 0.20+/0.6+ | 异步 SQLite / 向量存储 |
| OCR | `pytesseract`, `pillow` | 0.3+/12.2+ | 微信图片识别 |
| 嵌入 | `fastembed` | 0.8+ | 本地文本嵌入 |

### 3.2 开发工具链

| 工具 | 版本 | 用途 |
|------|------|------|
| `pytest` | 9.0+ | 测试框架（12,058 用例） |
| `pytest-asyncio` | 1.3+ | 异步测试支持 |
| `pytest-cov` | 6.0+ | 覆盖率统计 |
| `mypy` | 1.13+ | 静态类型检查（strict 模式） |
| `ruff` | — | Linting（E/F/W 规则） |
| `debugpy` | 1.8+ | 调试支持 |

### 3.3 可选功能包（extras）

```
[wechat]        — 微信网关（aiohttp, qrcode, cryptography）
[mcp]           — MCP 协议支持
[embeddings]    — 嵌入模型
[vectors]       — 向量数据库
[observability] — LangFuse 可观测
[eval-deepeval] — DeepEval 评估
[eval-ragas]    — Ragas RAG 评估
[web]           — 网页抓取
[notify]        — Apprise 通知
[voice]         — 语音输入/输出
[pty]           — 伪终端支持
```

---

## 四、关键数据流

### 4.1 入站请求处理（微信 → Agent Loop）

```
微信消息
    │
    ▼
wechat_ilink.phases  (协议层)
    │  - QR 登录 / 轮询 / 发送
    │
    ▼
message_handler.py  (网关层)
    │  - 会话路由 (session_registry)
    │  - 入站校验 (inbound_validate)
    │  - 幂等去重 (inbound_idempotency)
    │
    ▼
message_queue.py  (队列层)
    │  - 优先级队列 (now/next/later)
    │  - 策略模式 (followup/collect/interrupt/steer)
    │
    ▼
Orchestrator  (编排层)
    │  - 系统提示注入
    │  - 模型配置 (prompt_assembler)
    │  - Skill 路由 (skill_bridge)
    │  - 记忆预取 (memory_bridge)
    │
    ▼
AgentLoop.run()  (认知环)
    │  - prepare → LLM → tools → finalize
    │
    ▼
outbound_bridge  (出站)
    │  - 回复发送
    │  - 完成通知
    │  - 补充回复
    │
    ▼
微信用户
```

### 4.2 记忆系统数据流

```
PostToolUse 事件
    │
    ▼
ObservationStore  (派生索引)
    │  - 内容哈希去重
    │  - TTL/retention
    │
    ▼
向量化 (embedding)
    │
    ▼
VectorStore (ChromaDB)
    │  - 语义索引
    │  - 分片 (chunking)
    │
    ▼
RecallRouter (查询时)
    │  - 多路召回 (query_decompose)
    │  - 相关性排序 (retrieval_ranking)
    │  - 上下文裁剪 (recall_scopes)
    │
    ▼
Agent Loop 上下文注入
```

### 4.3 委派流程（Delegate）

```
主 Agent (ButlerAgent)
    │  - 解析用户意图为子任务
    │
    ▼
delegate_task 工具
    │  - 创建子 Agent 实例
    │  - 隔离历史 (最大深度 3)
    │  - 限制工具集
    │
    ▼
子 AgentLoop (独立对话)
    │  - 继承 system prompt（cache-safe）
    │  - 独立执行上下文
    │
    ▼
结果汇总 (delegate_report)
    │  - 字符预算 (summary_budget)
    │  - 注入父上下文
    │
    ▼
主 Agent 继续执行
```

---

## 五、测试基础设施

### 5.1 测试分层

| 层级 | 标记 | 说明 | 示例 |
|------|------|------|------|
| L1 单元测试 | `unit` | 快速、无 I/O | 纯函数逻辑 |
| L2 模块测试 | `module_test` | Mock I/O | 数据库/网络 mock |
| L3 集成测试 | `integration` | 跨模块 | 多管线协同 |
| L4 端到端 | `e2e` | 完整管线 | 全流程验证 |
| 特殊 | `live_llm` | 需要真实 LLM API | 在 CI 中被排除 |
| 特殊 | `corpus` | 语料库驱动评估 | 回归测试 |
| 特殊 | `gateway` | 网关域测试 | 微信相关 |
| 特殊 | `dev_engine` | 开发引擎测试 | 代码级验证 |

### 5.2 测试统计

- **总用例**：12,058 可收集用例（另有 545 因 marker 被排除）
- **大测试文件**：11 个测试文件 > 800 行（最大 1,277 行）
- **全量测试**：`PYTHONPATH=. pytest tests/` 需数分钟完成
- **门禁脚本**：
  - `butler-pytest-fast-gate.sh` — smoke + gateway + CC harness + mypy
  - `butler-layer-import-gate.sh` — 1218 文件跨层 import 检查
  - `butler-mypy-strict-gate.sh` — 826 主模块 strict 检查

### 5.3 测试隔离问题

- 全局可变状态较多，测试间可能互相影响（如事件总线、权限状态）
- 建议引入 pytest fixtures 与 conftest 统一管理

---

## 六、技术债务与重构建议

### 6.1 架构级债务（高优先级）

| # | 问题 | 现状 | 影响 | 建议 |
|---|------|------|------|------|
| **TD-1** | **`core/` 与 `ops/` 耦合** | `core/` 中有 22 处 `from butler.ops` 导入 | 违反 L3→L9 单向依赖原则 | 引入事件总线，core 发事件，ops 订阅处理 |
| **TD-2** | **模块数量膨胀** | 1,490 个 Python 文件（299 在 core/）| 认知过载、导航困难 | 按功能域重组 core/ 子包 |
| **TD-3** | **配置项过多** | 200+ `BUTLER_*` 环境变量 | 维护困难、默认值不一致 | 引入配置 Schema + 校验，分级管理 |
| **TD-4** | **`_ops.py` 拆分模式** | 大量 `*_ops.py` 伴随文件用于 mypy strict | 增加文件数、分裂关注点 | 用 Protocol 或 TypedDict 类型注解替代 |
| **TD-5** | **循环依赖** | `task_orchestrator ↔ dag_scheduler` 检测到 | 潜在初始化问题 | 抽取公共接口到独立模块 |

### 6.2 代码级债务（中优先级）

| # | 问题 | 现状 | 建议 |
|---|------|------|------|
| **TD-6** | **全局单例过多** | 9 个 contracts Registry 都是模块级单例 | 引入依赖注入容器或上下文管理器 |
| **TD-7** | **惰性导入不完整** | `core/__init__.py` 已优化，但子包可能仍有急切导入 | 审计所有 `__init__.py` |
| **TD-8** | **测试文件过大** | 11 个 > 800 行，最大 1,277 行 | 按测试场景拆分 |
| **TD-9** | **无但ler包内大文件** | 代码文件均 < 800 行 ✓ | 保持 |
| **TD-10** | **硬编码** | 部分测试使用硬编码日期、时间戳 | 使用动态生成 |

### 6.3 设计级债务

| # | 问题 | 建议 |
|---|------|------|
| **TD-11** | **理论-工程映射复杂** | 两套 L1-L7 编号（产品域 vs 工程层），新成员理解门槛高 | 统一术语或在文档中增加对照表 |
| **TD-12** | **函数式编程不彻底** | `effects/` 模块提供了 Result/Maybe，但主流程仍大量使用 try/except | 逐步在核心路径采用代数错误处理 |
| **TD-13** | **事件溯源覆盖不全** | `contracts/events.py` 有基础实现，但仅部分模块使用 | 扩展到所有状态变更场景 |

### 6.4 性能级债务

| # | 问题 | 建议 |
|---|------|------|
| **TD-14** | **初始内存占用** | 已优化（惰性导入从 100MB+ 降至 0.9MB），但全量加载后仍约 115MB | 考虑使用子进程隔离不同功能域 |
| **TD-15** | **向量检索性能** | ChromaDB 在大规模数据下可能有瓶颈 | 评估 Milvus/Qdrant 等替代方案 |

---

## 七、重构建议路线图

### Phase 0：基础设施加固（低风险、高收益）

| 任务 | 优先级 | 工作量 | 收益 |
|------|--------|--------|------|
| 0.1 引入配置 Schema 校验 | P0 | 2 天 | 消除配置不一致 |
| 0.2 审计并统一 `__all__` 导出 | P0 | 3 天 | 明确公共 API |
| 0.3 清理 `from X import *` | P0 | 1 天 | 避免命名污染 |
| 0.4 完善 mypy strict 覆盖 | P1 | 5 天 | 类型安全 |
| 0.5 引入预-commit 钩子 | P1 | 1 天 | 自动门禁 |

### Phase 1：架构解耦

| 任务 | 优先级 | 工作量 | 收益 |
|------|--------|--------|------|
| 1.1 core→ops 依赖改为事件总线 | P0 | 5 天 | 解除 L3→L9 耦合 |
| 1.2 抽取公共接口层 | P0 | 3 天 | 消除循环依赖 |
| 1.3 引入依赖注入容器 | P1 | 5 天 | 替代模块级单例 |
| 1.4 core/ 子包重组 | P1 | 7 天 | 改善可导航性 |

### Phase 2：代码质量提升

| 任务 | 优先级 | 工作量 | 收益 |
|------|--------|--------|------|
| 2.1 测试文件拆分 | P1 | 3 天 | 改善可维护性 |
| 2.2 函数式错误处理推广 | P2 | 5 天 | 减少 try/except |
| 2.3 统一日志与指标 | P2 | 3 天 | 可观测性提升 |
| 2.4 文档自动生成 | P2 | 3 天 | 降低文档维护成本 |

### Phase 3：现代化演进

| 任务 | 优先级 | 工作量 | 收益 |
|------|--------|--------|------|
| 3.1 评估异步框架升级 | P2 | 5 天 | 改善并发性能 |
| 3.2 考虑 Monorepo 结构 | P2 | 10 天 | 多包独立版本管理 |
| 3.3 构建插件系统 | P3 | 7 天 | 增强可扩展性 |
| 3.4 引入 WASM 沙箱 | P3 | 10 天 | 更安全的代码执行 |

---

## 八、重构策略建议

### 8.1 渐进式重构

**核心原则**：不进行"大爆炸"式重写，而是按层逐步替换：

```
当前系统 ──→ Phase 0 (加固) ──→ Phase 1 (解耦) ──→ Phase 2 (质量) ──→ Phase 3 (演进)
    │                                        │
    └── 每阶段保持可用 ──────────────────────┘
```

### 8.2 关键决策点

| 决策 | 选项 A | 选项 B | 建议 |
|------|--------|--------|------|
| **Python vs 其他语言** | 继续 Python | 迁移到 Rust/Zig | **建议 A**：Python 生态成熟，迁移成本过高 |
| **Monorepo 结构** | 保持当前扁平 | 按包拆分 + workspace | **建议 B**：改善依赖管理 |
| **异步框架** | asyncio + httpx | AnyIO + starlette | **建议 A**：当前方案成熟 |
| **向量数据库** | ChromaDB | Qdrant/Milvus | **建议 A**：规模够用 |
| **测试框架** | pytest | pytest + hypothesis | **建议 B**：增加属性测试 |

### 8.3 保持稳定的策略

1. **保持 Port/Registry 契约** — `contracts/` 目录是稳定接口
2. **逐步迁移 `_ops.py`** — 用类型注解替代而非删除
3. **保留向后兼容 Shim** — 37 个 Shim 文件是有意的兼容层
4. **自动化门禁先行** — CI 检查在重构前就完善

---

## 九、总结

### 9.1 项目健康度评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **功能完备性** | ⭐⭐⭐⭐⭐ | 11 内置工具 + 丰富可选工具 |
| **架构清晰度** | ⭐⭐⭐⭐ | 九层模型清晰，但理论映射复杂 |
| **代码可维护性** | ⭐⭐⭐ | 模块过多、`_ops.py` 模式增加认知负担 |
| **测试覆盖度** | ⭐⭐⭐⭐ | 12,058 用例，但隔离性待改善 |
| **类型安全** | ⭐⭐⭐⭐ | mypy strict 覆盖面广 |
| **性能** | ⭐⭐⭐⭐ | 已优化惰性导入，全量加载后约 115MB |
| **可扩展性** | ⭐⭐⭐⭐ | Port/Registry 模式良好 |
| **文档质量** | ⭐⭐⭐⭐ | 详尽但分散 |

### 9.2 重构优先级 Top 5

1. **TD-1** — 解除 core→ops 耦合（架构基础）
2. **TD-3** — 配置收敛（稳定性基础）
3. **TD-6** — 依赖注入替代全局单例（可测试性基础）
4. **TD-2** — 模块重组（可导航性）
5. **TD-12** — 函数式错误处理（代码质量）

### 9.3 关键约束（重构时不可突破）

- **`contracts/` 目录**是稳定契约，不可随意修改
- **受保护文件**（loop.py 等）需人工 + 完整门禁
- **37 个 Shim 文件**是向后兼容层，不可删除
- **ENG-15 跨层 import 规则**必须持续通过
- **`pyproject.toml`** 需保持 mypy strict 配置
