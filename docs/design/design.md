# 管家系统（Butler System）完整设计方案

> 版本: v1.0 | 更新日期: 2026-05-20  
> 当前实现架构详见 [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md)；Hermes 提炼见 [`../architecture/hermes-extraction-map.md`](../architecture/hermes-extraction-map.md)。

## 目录

- [一、系统总览](#一系统总览)
- [二、核心架构（v4）](#二核心架构v4)
- [三、分层模型配置](#三分层模型配置)
- [四、项目级记忆系统](#四项目级记忆系统)
- [五、项目级 Session 隔离](#五项目级-session-隔离)
- [六、信息回传分层压缩协议（v4）](#六信息回传分层压缩协议v4)
- [七、DevAgent 能力体系](#七devagent-能力体系)
- [八、SubAgent 编排引擎](#八subagent-编排引擎)
- [九、参考系统分析](#九参考系统分析)
- [十、国产模型适配策略](#十国产模型适配策略)
- [十一、v0.5 深度优化升级](#十一v05-深度优化升级)
- [十二、v0.6 评审意见驱动的稳健性升级](#十二v06-评审意见驱动的稳健性升级)
- [十三、v0.7 分层记忆与 Skill 系统](#十三v07-分层记忆与-skill-系统)
- [十四、v0.8 Hermes 提炼路线图](#十四v08-hermes-提炼路线图)
- [十五、v0.9 run_agent 二次提炼](#十五v09-run_agent-二次提炼)
- [十六、v1.0 Loop 模块化与硬化观测](#十六v10-loop-模块化与硬化观测)

---

## 一、系统总览

### 1.1 设计背景

管家系统源于 AI-Incursion 项目原型，核心目标是构建一个**多项目 AI 开发协助系统**，使用户能通过 CLI 或微信指挥后台 AI 完成代码开发、内容创作等任务。

### 1.2 解决的痛点

| 痛点 | 问题 | 对策 |
|------|------|------|
| Claude Code 只支持自家模型 | 国产模型效果打折 | 自建 DevAgent，原生支持任意模型 |
| 同时只能用一个模型 | 不同任务需要不同模型 | 分层模型配置：管家/项目/Agent 各层独立 |
| Hermes+CC 交互体验差 | 跨进程通信不可靠 | 统一进程内 Agent Loop |
| SubAgent/Team 效果差 | 无精心设计的编排协议 | Agent 编排引擎：上下文传递、预算、聚合 |
| 切项目记忆混乱 | Session 不区分项目 | 项目级 Session 隔离 |
| 新会话丢失项目认知 | 记忆全在会话中 | 项目级持久记忆 |
| 信息回传过载 | Agent 输出信息量大 | 结构化多粒度报告 + 渐进式披露 |

### 1.3 三层架构

```
用户层          CLI / 微信
  ↕
管家层          Butler Agent（调度、路由、汇报）  ← 模型 A
  ↕
项目/Agent 层   DevAgent / ContentAgent / ReviewAgent  ← 模型 B/C/D
  ↕
工具层          文件读写、Shell、代码搜索、Git、模糊匹配 Patch
```

每层可独立配置模型。管家用 DeepSeek 调度，DevAgent 用 MiniMax 写代码，ContentAgent 用千问写中文。

---

## 二、核心架构（v4）

### 2.1 模块结构（v4 当前）

> 下文第十一～十二章等历史章节中的 `butler/agent/`、`AgentRunner` 路径为早期设计；**当前实现**以本树与 [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md) 为准。

```
butler/
├── core/                      # Agent Loop 栈
│   ├── agent_loop.py          # 主循环编排（~300 行）
│   ├── tool_batch.py          # 工具批次、envelope、guardrails
│   ├── llm_retry.py           # LLM 重试、schema 恢复、failover
│   ├── context_pipeline.py    # 压缩、hygiene、API 消息准备
│   ├── parallel_tools.py      # 并行批调度
│   ├── context_compressor.py  # 上下文压缩
│   ├── message_repair.py      # 消息序列修复
│   └── steer.py               # /steer 运行中指引
├── transport/                 # LLM 协议与 Provider（非 v1 executors/providers）
│   ├── llm_client.py
│   ├── chat_completions.py / anthropic_transport.py
│   ├── providers.py / fallback.py / error_classifier.py
│   └── schema_sanitizer.py
├── gateway/
│   ├── message_handler.py     # 入站消息、斜杠命令、/health
│   └── session_registry.py    # session 生命周期与审计桶清理
├── tools/
│   └── registry.py            # 工具注册、JSON envelope、审计
├── memory/                    # ButlerMemory + ProjectMemory
├── skills/                    # 加载、路由、合并、guard
├── task_orchestrator.py       # DAG 子 Agent 编排
├── orchestrator.py            # 管家编排入口
├── tool_guardrails.py         # 循环检测 block/warn/halt
├── post_session.py            # 会话后记忆 + Skill 提炼
├── agent_profiles.py          # dev/content/review 角色
├── report.py                  # AgentReport 渐进披露
├── config.py
└── main.py
```

### 2.2 自建 Agent Loop 替代 Claude Code / Hermes AIAgent

核心决策：**进程内自建 `AgentLoop`**（`butler/core/agent_loop.py`），不 `import` Hermes `AIAgent`，不依赖 Claude Code 子进程。

DevAgent / ContentAgent / ReviewAgent 通过 `orchestrator.create_agent_loop(role=...)` 以不同 `(model, tools, system_prompt)` 配置运行同一 Loop 栈。

主循环（编排层）每轮大致为：

1. `ContextPipeline.prepare_messages_for_api()` — 压缩、hygiene、repair  
2. `call_llm_with_retry()` — Transport + failover  
3. 有工具调用 → `process_tool_calls()` — 顺序/并行、guardrails、审计 envelope  
4. 纯文本 → 截断续写或完成  

DevAgent 工具集（节选）：`read_file`, `write_file`, `edit_file`, `search_code`, `run_shell`, Git 系列等 — 见 `butler/tools/`。

---

## 三、分层模型配置

### 3.1 三级配置合并

```
系统默认 → 管家层(.env/CLI) → 项目层(project.yaml) → Agent层(运行时)
```

每级非空字段覆盖上一级：

```python
@dataclass
class ModelConfig:
    provider: str = ""   # "claude" | "deepseek" | "qwen" | "minimax"
    model: str = ""      # "deepseek-v4-pro" | "minimax-m2.7"
    temperature: float | None = None
    max_tokens: int | None = None
```

### 3.2 project.yaml 扩展

```yaml
name: "灵文"
type: "content"
models:
  dev_agent:
    provider: "minimax"
    model: "minimax-m2.7"
  content_agent:
    provider: "qwen"
    model: "qwen-max"
```

### 3.3 /model 命令

```
/model                         → 查看各层模型配置
/model butler deepseek:deepseek-v4-pro
/model dev minimax:minimax-m2.7
/model content qwen:qwen-max
```

CLI 和微信均支持。项目级配置持久化到 `project.yaml`，管家级持久化到 `~/.butler/config.yaml`。

---

## 四、项目级记忆系统

### 4.1 三层记忆架构

| 层级 | 存储位置 | 内容 | 生命周期 |
|------|---------|------|---------|
| 全局记忆 | `~/.butler/memory/` | 主公偏好、跨项目经验 | 永久 |
| 项目记忆 | `projects/X/.butler/memory/` | 架构决策、代码模式、已知问题 | 随项目 |
| 会话记忆 | SQLite sessions 表 | 临时对话历史 | 会话内 |

### 4.2 自动提炼机制

会话结束时（`/new`、`/quit`），Butler 自动用 LLM 从对话历史中提取重要信息，写入项目记忆的对应章节。下次新会话，项目记忆注入 system prompt，Agent 立刻拥有完整项目认知。

### 4.3 System Prompt 注入顺序

```
[管家系统指令]
[全局记忆 - 主公偏好]
[当前项目记忆 - 架构/决策/模式]  ← 关键
[当前模型配置信息]
[对话历史]
```

---

## 五、项目级 Session 隔离

Session 以 `(platform, chat_id, project)` 为 key（实现：`butler/session_keys.py` → ``{platform}:{chat_id}:{project}``，无项目时用 ``_``）：

- 切换项目时自动切换到对应 Session（**不** `reset_all` 清空其它项目历史）
- 每个项目的对话历史完全独立（Gateway `session_registry` + CLI `loops_by_session`）
- 不会出现跨项目 AgentLoop 历史混乱（Butler/项目记忆层仍共享，见租户隔离路线图）

**项目工具白名单**（`project.yaml` → `tools`，实现：`butler/tools/project_tools.py`）：

- 非空时过滤管家与 `delegate_task` 子 Agent 的 OpenAI tools 列表
- 管家额外保留 `delegate_task`、`skills_list`、`skill_view`
- 常见别名：`edit_file`→`patch`，`search_code`→`search_files`，`run_shell`→`terminal`

---

## 五点五、租户（公司）边界

多公司共用一台 Butler 时，**全局**记忆与技能按租户隔离（实现：`butler/tenant.py`）：

| 资源 | 路径 / 规则 |
|------|-------------|
| Owner profile + experience | `~/.butler/tenants/{tenant}/memory/`（独立 SQLite） |
| 租户级 Skill | `~/.butler/tenants/{tenant}/skills/`（项目 `.butler/skills` 仍可覆盖同名技能） |
| 项目级记忆 | 仍在 `projects/<dir>/.butler/memory/`（随项目 workspace，不按租户再分库） |

**配置**：

- `project.yaml` → `tenant: acme`（可选；省略则继承 `~/.butler/config.yaml` 的 `default_tenant`，再否则为 `default`）
- 首次启动会把旧版 `~/.butler/memory`、`~/.butler/skills` 自动迁到 `tenants/default/`

**行为**：`/切换` 到另一租户下的项目时，`ButlerOrchestrator.butler_memory` 与 Skill 路由自动切换到对应租户存储；不同租户的 experience 互不可见。

**个人助手部署**：不必配置 `tenant` / `default_tenant`，全部使用 `default` 即可；多租户能力仅为未来多组织预留。

---

## 五点六、项目工作流（DAG）

`project.yaml` → `workflows` 与 `TaskOrchestrator.execute_graph` 对接（实现：`butler/workflows/`）：

| 来源 | 说明 |
|------|------|
| `project.yaml` | `name` + 可选内联 `steps[]`（`id` / `role` / `task` / `depends_on`） |
| `.butler/workflows/<name>.yaml` | 项目 workspace 内覆盖/扩展步骤 |
| `butler/workflows/builtin/` | 仅登记名称时合并内置模板（如 `novel-factory` 两阶段验收流） |

**触发**：`/工作流 list`、`/工作流 run <名称> [说明]`（微信同义）；管家工具 `run_workflow`。执行后写入 `AgentReport` 缓存，可用 `/详细` 钻取。

**钩子**：`project_switched` 在 HookBus 上广播（日志 + 可选上下文）；系统提示中附带「项目工作流」列表。

---

## 六、信息回传分层压缩协议（v4）

### 6.1 问题

Agent 执行一个任务可能有 15+ 轮工具调用，产出大量细节。如何向用户汇报？

### 6.2 结构化多粒度报告

Agent 完成任务后输出 JSON 结构化报告：

```python
@dataclass
class AgentReport:
    headline: str         # 一句话（<=50字）
    changes: list[Change] # 文件变更列表
    decisions: list[str]  # 关键决策
    issues: list[str]     # 需关注的问题/风险
    summary: str          # 完整详细总结
```

### 6.3 渠道差异化呈现

| 维度 | CLI | WeChat |
|------|-----|--------|
| 默认粒度 | headline + 变更列表 + 决策 | headline + 变更数 + issues |
| 进度流 | 实时步骤显示 | 里程碑推送（>=30s 间隔） |
| 钻取 | `/detail [section]`（`changes`/`decisions`/`issues`，中文别名） | `/详细` 或 `/详细 变更` 等；委派回合默认紧凑摘要 |

### 6.4 渐进式披露

用户看到简要汇报后可钻取：
- `/detail` → 完整报告
- `/detail changes` → 文件变更详情
- `/detail decisions` → 决策链
- `/detail log` → 执行步骤日志

---

## 七、DevAgent 能力体系

### 7.1 工具能力矩阵

| 工具 | 能力 | 关键特性 |
|------|------|---------|
| `edit_file` | 精确/模糊文件编辑 | 6 级模糊匹配策略、写后自动 lint、读取状态检查 |
| `search_code` | 代码搜索 | 基于 ripgrep、正则、文件过滤、Python 回退 |
| `read_file` / `write_file` | 文件读写 | 偏移量读取、目录自动创建 |
| `run_shell` | Shell 执行 | 超时控制、输出截断 |
| `git_status/diff/log/add/commit/branch` | Git 操作 | 完整 diff 输出、分离暂存与提交 |

### 7.2 模糊匹配引擎（参考 Hermes fuzzy_match.py）

当 `edit_file` 的 `old_text` 无法精确匹配时，依次尝试：

1. **精确匹配** — 直接字符串查找
2. **空白归一化** — 将连续空白折叠为单个空格后匹配
3. **缩进归一化** — 忽略行首缩进差异
4. **Unicode 归一化** — 处理全角/半角、弯引号/直引号
5. **锚点匹配** — 用首尾行锚定范围
6. **上下文匹配** — 用周围代码行定位

### 7.3 循环检测防护（参考 Hermes ToolCallGuardrails）

检测以下模式并介入：
- 相同参数重复调用同一工具 >= 3 次
- 连续 5 轮无文件变更（无进展）
- 相同错误反复出现

介入方式：注入提示引导 Agent 换策略，或在阈值后强制停止。

### 7.4 并行工具执行

读操作（`read_file`, `search_code`, `git_status`, `git_diff`, `git_log`）可并行执行。写操作（`edit_file`, `write_file`, `run_shell`, `git_commit`）串行。

### 7.5 Prompt 工程策略

**模型感知引导**：针对国产模型注入工具使用强制规则：

```
你必须使用工具来执行操作，不要描述你会做什么。
当你决定要修改文件时，立即调用 edit_file，不要先说"我会修改..."。
每次修改后必须验证：读取文件确认改动、运行相关测试。
```

**工作流示例**：在 system prompt 中放入典型工作流，帮助国产模型理解 tool calling 模式。

---

## 八、SubAgent 编排引擎

### 8.1 数据结构

```python
@dataclass
class AgentSpawnConfig:
    role: str           # "dev" | "content" | "review"
    task: str           # 任务描述
    tools: list[str]    # 工具子集
    model_config: ModelConfig
    max_turns: int = 30
    context: str = ""   # 父 Agent 传入的上下文

@dataclass
class AgentResult:
    success: bool
    response: str
    report: AgentReport   # 结构化报告
    artifacts: list[str]  # 产出物路径
    turns_used: int
    tokens_used: dict
```

### 8.2 编排模式

- **单任务**: `spawn_agent(config)` — 等待完成
- **并行**: `spawn_parallel([config1, config2])` — 多 Agent 同时工作
- **串行**: `spawn_sequential([cfg1, cfg2], pass_context=True)` — 链式传递上下文
- **后台**: `spawn_background(config, on_complete)` — 异步执行

---

## 九、参考系统分析

### 9.1 Hermes Agent 关键技术

| 技术 | 描述 | 我们的借鉴 |
|------|------|-----------|
| 多策略模糊匹配 | `fuzzy_match.py` 6 级降级策略 | 直接参考实现 fuzzy_match |
| 工具使用强制 | 对非 Claude 模型注入强制规则 | 适配到国产模型 prompt |
| ToolCallGuardrails | 循环检测 + 进展监控 | 实现 tool_guardrails.py |
| execute_code | 编程式批量工具调用 | 暂列为未来扩展 |
| 渐进式上下文 | 探索新目录自动加载规则 | 暂列为未来扩展 |
| 并行工具执行 | 读并行、写串行 | 已在升级计划中 |
| Patch 工具 | replace 和 unified diff 两种模式 | 实现为增强版 edit_file |

### 9.2 Claude Code 关键技术

| 技术 | 描述 | 我们的借鉴 |
|------|------|-----------|
| 读后才能编辑 | readFileState + mtime 检查 | 实现 read_state 跟踪 |
| 引号归一化 | 弯引号 ↔ 直引号 | 纳入模糊匹配策略 |
| 流式工具执行 | 不等回复完成就开始执行 | 暂列为未来扩展 |
| autocompact | 自适应上下文压缩 | 暂列为未来扩展 |
| Prompt 缓存 | 静态前缀 / 动态后缀分离 | 已在架构中实现 |
| 结构化 diff 反馈 | 编辑后返回 diff | 已在 edit_file 中实现 |

---

## 十、国产模型适配策略

### 10.1 为什么传统模型蒸馏不实际

- 需要大量 agent 轨迹数据（采集成本高）
- 需要微调基础模型（国产 API 通常不支持）
- 维护成本高（模型更新需重新蒸馏）

### 10.2 等效替代方案

**Prompt 蒸馏**：从 Claude Code / Hermes 的 system prompt 提取最有效的行为规则，适配到我们的 prompt。

**工具侧补偿**：让工具更"聪明"，降低对模型推理能力的依赖：
- 模糊匹配减少编辑失败率
- 自动 lint 捕获语法错误
- 丰富的错误信息帮助模型自我纠正
- 循环检测主动介入

**任务分解策略**：Butler 层做更精细的任务分析，将复杂任务拆为国产模型可靠完成的小步骤。

**Few-shot 工具示例**：在 system prompt 中放入工具调用的成功案例，引导模型正确使用。

---

## 十一、v0.5 深度优化升级

### 11.1 语义知识图谱记忆系统

升级 `butler/storage/memory_store.py`，从纯 Markdown 截取升级为三层混合检索：

- **FTS5 全文搜索**：记忆条目存入 SQLite，使用 FTS5 做 BM25 语义搜索，`get_relevant_context(query)` 按任务语义匹配 top-K 记忆
- **知识三元组**：提取 `(主体, 关系, 客体)` 存入 triplets 表，支持图查询
- **Ebbinghaus 衰减**：`decay_memories(half_life_days=30)` 让旧记忆权重自然下降
- **访问计数**：高频使用的记忆自动提权
- MEMORY.md 继续作为人类可读导出

### 11.2 DAG 图状态机编排引擎

升级 `butler/core/task_orchestrator.py`：

- **TaskNode** + DAG 依赖：用 `depends_on` 定义任务依赖关系
- **拓扑排序并行执行**：Kahn's 算法分层，无依赖任务并行
- **条件路由**：`router: Callable[[AgentResult], str]` 根据结果动态选择下一步
- **Human-in-the-loop**：`requires_approval=True` 暂停等待用户审批
- **检查点恢复**：`resume_graph()` 从审批暂停处继续

### 11.3 Plan-then-Execute 混合模式

新增 `AgentRunner.run_planned()` 方法：

- Phase 1：规划阶段（不调工具），让 Agent 先输出编号计划
- Phase 2：执行阶段（带工具），按计划逐步执行
- 适合 >10 步的复杂任务（Plan-Execute 准确率 92% vs ReAct 85%）
- 定期反思注入：每 8 轮插入自我反思提示

### 11.4 自我验证闭环

新增 `butler/agent/verify_loop.py`：

- 编辑文件后自动发现对应测试文件
- 支持 Python（pytest）、JavaScript/TypeScript（jest）
- 测试失败时将结果注入 Agent 上下文引导修正
- 参考 TDAD 论文：回归率从 6.08% 降至 1.82%

### 11.5 Tree-sitter 代码图谱

新增 `butler/tools/code_graph.py`：

- AST 索引：函数/类/导入/调用关系存入 SQLite
- 工具 `code_graph_index`：索引项目代码结构
- 工具 `code_graph_query`：查询 find_symbol/find_callers/find_imports/impact_analysis/project_map
- 参考 Codebase-Memory 论文：83% 答案质量，10x 更少 tokens

### 11.6 MCP 协议支持

新增 `butler/mcp/server.py`：

- **MCPServer**：将 Butler 工具暴露为 MCP Server（JSON-RPC 2.0 over stdio），支持 Cursor/VS Code 等 MCP 客户端直接调用
- **MCPClientBridge**：消费外部 MCP Server，将其工具注册到 Butler 工具注册表
- 实现 initialize/tools_list/tools_call 协议子集

### 11.7 Git Worktree 隔离

新增 `butler/tools/worktree_tools.py`：

- `worktree_create`：为并行 Agent 创建隔离工作树
- `worktree_merge`：任务完成后合并回主分支
- `worktree_remove`：清理已完成的工作树
- 每个 Agent 在独立目录工作，物理层面防止文件冲突

### 11.8 结构化 Trace 系统

新增 `butler/agent/trace_store.py`：

- `TraceRecord` + `TraceSpan`：完整记录每次 Agent 执行的轨迹
- `TraceStore`：持久化到 SQLite，支持查询和统计
- `TraceCollector`：轻量级数据收集器，集成到 AgentRunner
- `get_stats()`：成功率、平均轮次、token 消耗、工具调用分布

### 11.9 ACI 优化

升级 `butler/tools/file_tools.py`：

- 窗口化文件查看：大文件默认只返回前 150 行（参考 SWE-agent ACI 研究：仅接口优化提升 10.7 个百分点）
- 空输出显式标注：空文件返回 "(文件为空)"，空目录返回 "(目录为空)"
- 目录条目限制：超过 200 条自动截断

---

## 十二、v0.6 评审意见驱动的稳健性升级

基于 5 份独立评审意见的共识分析，重点加固系统稳定性、安全性和可运维性。

### 12.1 Tool Calling 容错重试

新增 `butler/agent/tool_call_repair.py`，集成到 AgentRunner：

- `repair_json()`：5 种策略修复损坏的 JSON（尾逗号、单引号、未闭合括号、嵌入在文本中的 JSON）
- 模型输出解析失败时自动构造纠正提示返还给模型，最多重试 2 次
- `validate_tool_call()`：校验参数完整性，自动类型转换（string→int 等）

### 12.2 模糊匹配置信度阈值

升级 `butler/tools/fuzzy_match.py`：

- 高级模糊策略（block_anchor、context_aware）增加 SequenceMatcher 置信度计算
- 置信度低于 75% 时拒绝执行，返回："请先用 read_file 查看文件最新内容，再提供更精确的 old_text"
- 防止误匹配引入隐蔽逻辑 bug（评审 4 号重点关注）

### 12.3 Worktree 冲突检测与解决

升级 `butler/tools/worktree_tools.py`：

- 合并前使用 `git merge --no-commit --no-ff` 做试探性合并
- 检测到冲突时自动 `merge --abort`，返回冲突文件列表和 diff stat
- 新增 `worktree_diff` 工具查看具体差异
- 建议委托 ReviewAgent 处理冲突（5 位评审全部提出）

### 12.4 Provider 熔断与自动降级

新增 `butler/providers/circuit_breaker.py`：

- 三态状态机：CLOSED → OPEN → HALF_OPEN，标准熔断器模式
- 可配置失败阈值（默认 5 次/120s 窗口）、恢复超时（60s）
- `configure_fallback()`：设置降级链（如 deepseek → qwen → claude）
- `get_available_provider()`：自动选择可用 Provider

### 12.5 并发调度器与 LLM 限流

新增 `butler/agent/agent_scheduler.py`：

- `AgentScheduler`：Semaphore 控制最大并发 Agent 数（默认 3）
- `TokenBucket`：令牌桶算法限制每秒 LLM 调用频率
- 按 Provider 独立配置限流策略
- 防止并行 SubAgent 耗尽 API rate limit

### 12.6 记忆审核机制

升级 `butler/storage/memory_store.py`：

- `classify_memory()`：关键词分类——事实性记忆自动写入，决策性记忆标记待审核
- `PENDING_DECISIONS.md`：存储待审核记忆，用户通过 `/approve` 确认
- `approve_pending()` / `reject_pending()`：批量审批或拒绝
- 防止 Agent 幻觉决策被永久存入记忆库（评审 1/3/4 重点关注）

### 12.7 Trace 自动清理

升级 `butler/agent/trace_store.py`：

- `cleanup(max_age_days=30, max_records=1000)`：按年龄和数量双维度清理
- `auto_cleanup()`：DB 超过 50MB 时自动触发
- 初始化时自动执行，防止磁盘膨胀

### 12.8 动态重规划

升级 `butler/executors/agent_runner.py` 的 `run_planned()` 方法：

- 跟踪连续失败次数，达到 3 次时触发动态重规划
- 注入重规划提示让 Agent 暂停、分析失败原因、调整计划
- 避免"计划赶不上变化"的硬执行问题（评审 4/5 提出）

### 12.9 Token 预算控制

新增 `butler/agent/token_budget.py`：

- 任务级预算（默认 50 万 tokens）和日预算（默认 500 万 tokens）
- 按 Provider 估算费用（内置主流模型价格表）
- 达到 80% 时警告，超限时拒绝执行
- `get_daily_summary()`：每日用量统计

### 12.10 轻量级 Event Bus

新增 `butler/core/event_bus.py`：

- 异步发布/订阅模式，支持装饰器 `@event_bus.on("agent.completed")`
- 一次性订阅 `once()`、通配符 `*` 订阅
- 事件历史记录（最近 100 条）
- 解耦组件间通信，为 webhook、审计日志预留扩展点

---

## 十三、v0.7 分层记忆与 Skill 系统

### 13.1 分层记忆系统

将原来的单一 `MemoryStore` 拆分为管家层和项目层两套独立记忆系统，各有不同的 schema、检索策略和生命周期。

**管家层记忆** (`butler/storage/butler_memory.py`)：
- `ProfileStore`（`owner_profile.md`）— 有界文本存储（2000 字符上限），支持 add/replace/remove 三种操作，含 prompt 注入检测
- `ExperienceStore`（`experience.db`）— SQLite + FTS5 跨项目经验存储，BM25 语义检索，按当前项目上下文匹配相关经验
- `CommPrefs`（`communication.md`）— 渠道偏好（500 字符上限）

**项目层记忆** (`butler/storage/project_memory.py`)：
- `MarkdownMemory`（`MEMORY.md`）— 结构化 5 section（架构/决策/模式/问题/状态），决策自动分类 + 待审核机制
- `SemanticMemoryIndex`（`knowledge.db`）— FTS5 + 知识图谱三元组，复用底层组件
- `ProjectFactsStore`（`facts.json`）— 从代码自动提取技术事实（扫描 pyproject.toml/package.json/go.mod），不依赖 LLM
- `get_context_for_agent(role, task)` — 按 Agent 角色返回不同粒度的记忆（DevAgent 看架构+代码模式，ContentAgent 看状态+已知问题）

**记忆工具** (`butler/tools/memory_tools.py`)：
- `remember` 支持三通道写入：`butler`（管家偏好）、`project`（项目技术）、`experience`（跨项目经验）
- `recall` 按 scope 分层查询
- `approve_memory` 审核待批准的决策记忆

### 13.2 Skill 系统

Skill 是**可复用的操作流程**（长篇指令），与记忆（短条事实/偏好）有明确边界。参考 hackthon_alpha 的 Skill 引擎 + Hermes 的 Skill 生态设计。

**存储结构**：

```
~/.butler/skills/              # 全局 Skill（跨项目通用）
├── git-workflow/
│   └── SKILL.md
└── .usage.json

<project>/.butler/skills/      # 项目 Skill
├── add-api-endpoint/
│   └── SKILL.md
└── .usage.json
```

**SKILL.md 格式**（YAML frontmatter + Markdown body）：

```yaml
---
name: add-api-endpoint
description: 在灵文项目中添加新的 API 端点
triggers:
  - "添加接口"
  - "新建 API"
tools:
  - read_file
  - edit_file
scope: project
---

## 工作流程
### 1. 确认路由文件
...
```

**Skill 引擎模块** (`butler/skills/`)：

| 模块 | 职责 |
|------|------|
| `loader.py` | 双目录扫描（project + global），轻量 YAML frontmatter 解析，按 scope 过滤 |
| `similarity.py` | **三层漏斗**相似度检测：Trigger 集合 Jaccard (≥0.3) → TF-IDF 余弦 (≥0.5) → LLM 语义判断 (≥0.7) |
| `consolidator.py` | LLM 驱动的 Skill 合并：取 triggers/tools 并集，合并 body，生成统一 name/description |
| `manager.py` | 生命周期管理：**创建时自动触发相似度检测 → 自动合并**，编辑/删除/patch，归档旧 skill 到 `.archive/` |
| `extractor.py` | 会话后自动提炼：分析对话记录识别可复用工作流，返回 ≤2 个候选 skill（含 scope 判定） |
| `usage.py` | `.usage.json` 使用统计：views/uses/created_at/source，合并时累加计数 |
| `router.py` | **运行时热路径匹配**（无 LLM）：Trigger 关键词匹配 → TF-IDF 余弦，返回 top-K 匹配的 skill body 注入 Agent 上下文 |

**自动合并流程**（核心创新，从 hackthon_alpha 移植）：

```
skill_create("new-skill", ...)
    │
    ▼
SkillManager.create()
    │
    ▼
SkillSimilarity.find_similar(new_skill, existing_skills)
    │
    ├── Layer 1: Trigger Jaccard ≥ 0.3 → 候选
    ├── Layer 2: TF-IDF Cosine ≥ 0.5 → 候选
    └── Layer 3: LLM 判断 confidence ≥ 0.7 → 确认
    │
    ▼ (有相似 skill)
SkillConsolidator.merge([new_skill] + similar_skills)
    │
    ├── LLM 生成合并后的 name/description/triggers/tools/body
    ├── 归档旧 skill → .archive/<name>_<timestamp>/
    ├── 写入合并后的 SKILL.md
    └── UsageTracker.on_merge() 累加统计
    │
    ▼ (无相似 skill 或合并失败)
直接创建新 skill → UsageTracker.on_create()
```

**集成到 Butler 工作流**：

1. **任务分发**：`executor_tools._delegate()` 调用 `_match_skills_for_task()`，通过 `SkillRouter` 匹配相关 skill body 注入 Agent 上下文
2. **会话结束**：`Butler.close()` 调用 `PostSessionProcessor`，双通道提炼——记忆通道 + skill 提炼通道
3. **Agent 工具**：`skill_list`/`skill_view`/`skill_create` 注册为 Agent 可用工具，`skill_create` 走 `SkillManager` 保证自动合并

### 13.3 工具系统增强

扩展 `ToolEntry`，支持 scope/safety_level/read_only 元数据：

```python
@dataclass
class ToolEntry:
    name: str
    description: str
    parameters: dict
    handler: ToolHandler
    is_async: bool = False
    category: str = "general"
    scope: str = "global"        # "global" | "project" | "agent"
    safety_level: str = "safe"   # "safe" | "cautious" | "dangerous"
    read_only: bool = False      # True = 可并行执行
```

新增 `resolve_tools_for_agent(project_name, role)` 动态组装工具集：基于 Agent 角色 profile + 项目配置的 include/exclude + Skill 工具（始终可用）。

### 13.4 会话后双通道提炼

`PostSessionProcessor` (`butler/post_session.py`) 在会话结束时运行：

- **记忆通道**：LLM 分析对话记录，提取用户偏好 → ButlerMemory，项目技术细节 → ProjectMemory（事实直接写，决策待审核），跨项目经验 → ExperienceStore
- **Skill 通道**：LLM 识别可复用工作流 → `skill_create` → `SkillManager`（触发自动合并检测）

---

## 十四、v0.8 Hermes 提炼路线图

基于 `reference/hermes-agent` 源码深读，按「高 ROI、低耦合」分 4 个 Sprint 接入 Butler v4（详见 [`../architecture/hermes-extraction-map.md`](../architecture/hermes-extraction-map.md)）：

| Sprint | 内容 | 状态 |
|--------|------|------|
| 1 | Loop 生产化：guardrails、error_classifier、message_repair、fallback | ✅ 已完成 |
| 2 | 上下文压缩 + auxiliary_client | ✅ 已完成 |
| 3 | 并行工具、interrupt、delegate 安全信封 | ✅ 已完成 |
| 4 | 会话边界、HookBus、skills_guard 混合策略 | ✅ 已完成 |

**不移植**：`run_agent.py` 单体、`gateway/run.py`、Hermes 50+ 工具生态、SessionDB。

---

## 十五、v0.9 run_agent 二次提炼

针对 [`reference/hermes-agent/run_agent.py`](reference/hermes-agent/run_agent.py) 中 `AIAgent` 控制平面，已完成第二轮模块化提炼（详见 [`../architecture/hermes-extraction-map.md`](../architecture/hermes-extraction-map.md)「run_agent 二次提炼」表）：

| Sprint | 内容 | 状态 |
|--------|------|------|
| A | 输出/消息卫生、工具归一化、空内容重试 | ✅ |
| B | 可中断 API、steer、failover 回合恢复 | ✅ |
| C | 委派回调透传、截断续写 | ✅ |
| D | 文档更新 | ✅ |
| E | AgentLoop 模块化阶段 1–2 | `tool_batch` / `llm_retry` / `context_pipeline` 从 `agent_loop` 抽出 | ✅ |
| F | 硬化与观测闭环 | 审计生命周期、顺序/并行 interrupt、guardrail JSON、无 context 审计归属、`/health`、真实 API smoke | ✅ |

---

## 十六、v1.0 Loop 模块化与硬化观测

在 v0.9 控制平面提炼基础上，完成 Loop **编排与子模块拆分**及 **生产观测** 闭环（详见 [`../architecture/hermes-extraction-map.md`](../architecture/hermes-extraction-map.md) 表末行）：

| 主题 | 要点 |
|------|------|
| 模块化 | `agent_loop.py` ~298 行编排；`tool_batch` / `llm_retry` / `context_pipeline` / `parallel_tools` 独立单测 |
| 工具审计 | session 分桶；`on_session_removed` 与 reset/evict 对齐；`get_audit_session_key()` |
| Guardrails | `RLock` 线程安全；warn 写入 JSON `guardrail` 字段；halt 后 `precheck_tool` 跳过后续 dispatch |
| Gateway | `/health`、`/诊断`；无 health 快照时仍展示工具审计摘要 |
| 测试 | **925 passed**（默认排除 13 项 `live_llm`）；可选 `BUTLER_RUN_REAL_API_SMOKE=1` |

架构约束：`agent_loop.py` **< 400 行**；新能力优先落入子模块，避免回灌单体 `run_agent.py` 风格文件。

---

## 附录：命令速查

| 命令 | 说明 |
|------|------|
| `/projects` | 列出所有项目 |
| `/switch <名称>` | 切换项目（会话自动隔离） |
| `/model` | 查看各层模型配置 |
| `/model butler <p:m>` | 设置管家模型 |
| `/model dev <p:m>` | 设置 DevAgent 模型 |
| `/detail` | 查看上次 Agent 完整报告 |
| `/detail changes` | 查看文件变更详情 |
| `/detail decisions` | 查看关键决策 |
| `/detail log` | 查看执行步骤日志 |
| `/new` | 新会话（自动提炼旧会话记忆） |
| `/status` | 查看系统状态 |
| `/health`、`/诊断` | 运行时诊断（压缩、schema、Skill、工具审计摘要）|
| `/steer <文本>` | 向运行中 Agent 插入指引（不打断工具）|
| `/help` | 显示帮助 |
