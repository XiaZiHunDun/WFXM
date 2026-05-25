# 管家系统（Butler System）完整设计方案

> 版本: v4 产品设计摘要 | 更新日期: 2026-05-22  
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
- [附录：命令速查](#附录命令速查)
- [历史章节（v0.5–v1.0）](../history/design-evolution-v0.5-v1.0.md)

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
│   ├── tool_prune_policy.py   # 分级 micro 剪枝
│   ├── tool_result_storage.py # 大工具结果落盘
│   ├── read_state.py          # read-before-edit
│   ├── streaming_tools.py     # 流式只读预取
│   ├── cache_safe_delegate.py # 委派 prompt 前缀
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
│   ├── message_handler.py     # 入站消息、斜杠命令、队列 drain、/health
│   ├── message_queue.py       # 忙会话入站排队
│   ├── outbound_bridge.py     # typing、ack、completion、supplementary
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

> **实现对照与完善路线**（设计 vs 代码、网关识图边界、`/model` 持久化）：[`architecture/layered-model-config.md`](../architecture/layered-model-config.md)

### 3.1 三级配置合并（角色 LLM）

```
系统默认 → 管家层(.env/CLI) → 项目层(project.yaml) → 运行时(/model 等)
```

**正交层（不并入上式）**：`auxiliary.*`（压缩/记忆提取）、微信网关 VLM/STT（见 [`wechat-inbound-media.md`](../architecture/wechat-inbound-media.md)）。

**实现备注（2026-05-21）**：`butler/model_resolve.resolve_effective_model` 统一合并；厂长/Lead 与委派均含项目层；`/model` 支持 save/reset——见 [`layered-model-config.md`](../architecture/layered-model-config.md)。

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

CLI 和微信均支持。

**实现（M3）**：`/model save butler …` → `~/.butler/config.yaml`；`/model save dev_agent …` → 当前项目 `project.yaml`；无 `save` 为 runtime 临时。详见 [`layered-model-config.md`](../architecture/layered-model-config.md) §5.4。

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

| 技术 | 描述 | Butler v4 状态 |
|------|------|----------------|
| 读后才能编辑 | readFileState + mtime | ✅ `read_state.py`；`BUTLER_READ_BEFORE_EDIT` |
| 引号归一化 | 弯引号 ↔ 直引号 | ✅ `patch` 模糊匹配 |
| 流式工具执行 | 参数完整即执行只读工具 | ✅ `streaming_tools.py` + `BUTLER_STREAMING_TOOLS` |
| 上下文 micro / auto | 分级剪枝 + 阈值 LLM 摘要 | ✅ `tool_prune_policy` + `context_pipeline` |
| 大工具结果落盘 | persisted-output 指针 | ✅ `tool_result_storage.py` |
| Prompt 缓存 | 静态前缀 / 动态后缀 | ✅ `cache_safe_delegate.py`（委派子 loop） |
| 循环 transition | query 结束原因可观测 | ✅ `LoopTransitionReason` → `/诊断` |
| 结构化 diff 反馈 | 编辑后返回 diff | ✅ patch 结果摘要 |

详见 [`architecture/v4-architecture.md`](../architecture/v4-architecture.md) 与 [`plans/cc-butler-gap-analysis-2026-05.md`](../plans/cc-butler-gap-analysis-2026-05.md)。

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

> **历史路线图**（v0.5–v1.0 评审与 Hermes 提炼阶段）已迁至 [`../history/design-evolution-v0.5-v1.0.md`](../history/design-evolution-v0.5-v1.0.md)。

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
