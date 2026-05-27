# Claude Code 依赖深挖与 WFXM 提炼建议

> 范围：`reference/claude-code-bak/`（`claude-code/`、`claude-code-source-code/`、`claude-code-sourcemap/restored-src/`）  
> 目的：梳理 Claude Code 的真实依赖、存储/中间件/算法机制，并判断哪些能力适合 WFXM/Butler v4 吸收  
> 说明：本文件是分析材料，不代表已经实施；WFXM 架构与产品边界仍以 `docs/architecture/v4-architecture.md` 与 `docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md` 为准。

## 结论摘要

Claude Code 不应被理解成“一个依赖很多大中间件的 AI CLI”。它真正的强项不在数据库、中间件堆叠或重型基础设施，而在于把**上下文预算、工具并发、文件化持久化、权限决策、恢复能力**做成了统一的 agent loop 运行时。

从 `reference/claude-code-bak/` 三份代码看，最有价值的判断有四个：

1. **本地主持久化不是数据库优先，而是文件系统优先**：`JSONL transcript + JSON settings + Markdown memory + lockfile` 是主线。
2. **真实运行时依赖比公开 `package.json` 显示的要重得多**：Anthropic SDK、多云 provider、MCP、OAuth、GrowthBook、OpenTelemetry 等都在源码里。
3. **最值得学的是机制，不是依赖栈**：例如 tool result spill、micro/autocompact、只读工具并发、compact boundary、transition reason。
4. **WFXM 已经吸收了 Claude Code 很大一部分高价值模式**，后续更适合做局部增强，而不是重做为 Claude Code 形态。

## 1. 三份 Claude Code 代码的作用

### 1.1 目录分工

- `reference/claude-code-bak/claude-code/`
  - 更像源码归档与说明材料。
- `reference/claude-code-bak/claude-code-source-code/`
  - 带 `README`、`docs/` 的整理版，适合读架构说明与研究笔记。
- `reference/claude-code-bak/claude-code-sourcemap/restored-src/`
  - 从 sourcemap 还原出的源码树，最适合作为**实现依据**。

### 1.2 研究时应以哪份为准

本次分析以 `claude-code-sourcemap/restored-src/` 为主，因为它保留了：

- `query.ts`
- `services/tools/toolOrchestration.ts`
- `utils/sessionStorage.ts`
- `services/api/client.ts`
- `utils/permissions/permissions.ts`

这些文件足以直接验证 Claude Code 的 loop、工具编排、权限与持久化策略。

## 2. 依赖与基础设施剖面

### 2.1 公开包表面很薄，但真实依赖藏在 bundle 与源码中

`reference/claude-code-bak/claude-code-sourcemap/package/package.json` 表面上几乎没有运行时依赖，只有可选 `sharp` 二进制包。这意味着只看 npm manifest 会严重低估它的复杂度。

真实依赖主要通过源码 import 和动态 import 暴露出来。

### 2.2 LLM / Provider 栈

Claude Code 的核心模型接入不是单一 Anthropic API，而是一个多 provider 入口：

- `@anthropic-ai/sdk`
- `@anthropic-ai/bedrock-sdk`
- `@anthropic-ai/vertex-sdk`
- `@anthropic-ai/foundry-sdk`

同时还接入对应云厂商凭证体系：

- `google-auth-library`
- `@azure/identity`
- AWS 凭证刷新逻辑

这说明它把 provider 切换和 auth 刷新都放进了正式运行时，而不是外围脚本。

### 2.3 中间件 / 协议层

Claude Code 里真正有架构意义的“中间件”主要是：

- `@modelcontextprotocol/sdk`
  - MCP client / host / resource / auth
- `ws`
  - WebSocket 传输、桥接与远程能力
- `axios`
  - 远程设置、Teleport、session ingress 等 HTTP 能力
- OAuth 流程
  - Claude.ai 登录、token 刷新、MCP OAuth
- GrowthBook
  - feature gate、远程配置、缓存 gate 值
- OpenTelemetry
  - 可选 tracing / logs / metrics

### 2.4 原生与多媒体能力

从 `vendor/` 与 import 可以看到一些原生绑定：

- `audio-capture-napi`
- `image-processor-napi`
- `modifiers-napi`
- `sharp` 可选二进制

这些说明 Claude Code 的能力边界明显覆盖了桌面 / 语音 / 图像场景，而不只是 terminal coding agent。

## 3. 本地存储：主线不是数据库，而是文件系统

### 3.1 没有把 SQLite / Redis / Postgres 当本地主会话库

这次分析没有发现 Claude Code 把 SQLite、Postgres、Redis、LevelDB 作为**本地 CLI 主会话真相源**。

相反，它主要使用：

- `JSONL`
- `JSON`
- `Markdown`
- `proper-lockfile`
- `Map/LRU/memoize`

### 3.2 关键持久化对象

Claude Code 的本地主状态大致落在这些形态：

- 会话 transcript：`*.jsonl`
- 工具结果 spill：`tool-results/<toolUseId>.*`
- 项目 / 用户配置：`settings.json`、全局配置 JSON
- 长期记忆：`MEMORY.md` + 主题 Markdown 文件
- 任务 / 协作状态：每任务一个 JSON 文件
- cron / mailbox / 队列协调：JSON + lockfile

### 3.3 为什么这很重要

这表明 Claude Code 的设计哲学是：

- **append-only transcript 做事实源**
- **文件系统保存可恢复状态**
- **用轻量锁保证并发安全**
- **必要时把大结果 spill 到外部文件**

而不是“先上数据库，再围绕数据库做所有逻辑”。

对 WFXM 来说，这是一个很重要的信号：继续强化 `JSONL + 索引 + spill + observation 派生存储` 的路线，是合理的。

## 4. Claude Code 最强的不是依赖，而是运行时机制

### 4.1 上下文经济学

Claude Code 在主循环里把上下文预算做成了硬机制，顺序大致是：

1. tool result aggregate budget
2. microcompact
3. autocompact
4. reactive compact

这不是一个“出问题再兜底”的附加模块，而是每轮 query 的标准步骤。

### 4.2 工具编排

`services/tools/toolOrchestration.ts` 的核心思路非常清晰：

- 连续只读工具并发
- 写工具串行
- 通过 `isConcurrencySafe()` 显式判断工具是否可并发

这套规则比“简单地所有工具都并发/串行”更稳，也更容易调试。

### 4.3 transcript 恢复与 compact boundary

`utils/sessionStorage.ts` 显示 Claude Code 的 transcript 不只是日志文件，而是恢复模型的一部分：

- `parentUuid` 维护消息链
- `compact boundary` 是语义锚点
- 大 transcript 只读尾部 / 限制读取大小
- sidechain / agent transcript 有独立路径

这让 `/resume`、子 agent、compact 后恢复都能围绕同一事实源工作。

### 4.4 权限栈

Claude Code 的权限模型不是单层 allow/deny，而是多层组合：

- rule
- permission mode
- classifier（部分场景）
- user approval

这让它既能支持 headless / auto，也能支持显式人工门控。

### 4.5 诊断与 transition reason

`query.ts` 中的 `transition.reason` 很重要。它不是日志修饰，而是 loop 行为的正式状态：

- `reactive_compact_retry`
- `token_budget_continuation`
- `stop_hook_blocking`
- `next_turn`

这让问题排查和成本诊断都更直接。

## 5. 对 WFXM / Butler v4 最有价值的提炼点

结合 `docs/architecture/v4-architecture.md` 与当前 Butler 实现，Claude Code 里最值得继续提炼的是下面五项。

### 5.1 继续强化 `session_transcript.py`

Butler 已经有：

- `butler/core/session_transcript.py`
- transcript JSONL
- spill 指针
- transition reason

下一步值得继续增强的是：

- transcript 索引 / tail-read
- resume 视图
- queue / drain / compact 诊断的 transcript 可见性

这条线和 Claude Code 的真相源设计最接近，也最符合微信长会话场景。

### 5.2 保持 memory 主线的文件化，而不是主存储数据库化

Claude Code 证明长期 memory 完全可以以：

- `MEMORY.md`
- topic markdown
- 有界扫描
- 摘要 / 注入预算

来组织。

WFXM 已有 memory、observation、RAG 诊断和 `.butler/observations.db` 派生层，因此更适合继续做“文件主线 + 派生索引”，而不是把主记忆直接切换成全量消息数据库。

### 5.3 继续细化 tool result spill 与预算

Claude Code 的一个关键点是：**先控制 tool result 预算，再进入 compact**。

WFXM 已有：

- `butler/core/tool_result_storage.py`
- `enforce_message_tool_budget`

后续更值得做的是：

- per-tool 阈值继续细化
- spill 恢复展示更清晰
- `/诊断` 里把 budget / spill 命中更直观地暴露出来

### 5.4 显式化并发安全规则

Claude Code 用 `isConcurrencySafe()` 显式声明工具能否并发，这一点很值得 Butler 继续对齐。

WFXM 当前已有：

- `butler/core/parallel_tools.py`
- `butler/core/streaming_tools.py`

下一步可以继续统一：

- 哪些工具是并发安全
- 哪些工具需要串行
- 这些规则如何在 normal / streaming 两条路径复用

### 5.5 扩大 loop 可观测性，而不是扩大依赖面

Claude Code 值得学的是 transition 和状态显式化，不是默认接入 GrowthBook + OTEL + Datadog。

WFXM 更适合继续加强：

- `LoopTransitionReason`
- `/诊断`
- queue / drain / steer / stop hook 的状态展示

而不是为此引入整套外部观测平台。

## 6. 不建议从 Claude Code 继续吸收的部分

下面这些能力虽然在 Claude Code 中存在，但并不适合作为 WFXM 当前主线：

- 全量 MCP Host
- IDE bridge / desktop bridge
- Teleport / remote managed settings
- 多云 provider 全家桶
- GrowthBook + Datadog 默认接入
- 语音 / 桌面原生能力栈
- LLM 权限 classifier 默认化

原因很简单：这些能力服务的是 Anthropic 自己的产品形态，而 WFXM 当前边界是**微信单网关 + Butler 自建 loop + 薄 MCP 可选**。

## 7. 结合 WFXM 现状的最终判断

从 `docs/architecture/v4-architecture.md` 看，WFXM 已经有非常多 Claude Code 风格的高价值模块：

- `context_pipeline`
- `tool_result_storage`
- `parallel_tools`
- `streaming_tools`
- `session_transcript`
- `turn_token_budget`
- `reactive_compact`
- `permissions.py`

因此对 Claude Code 的正确吸收方式不是“再造一个 Claude Code”，而是：

1. **承认当前主线已基本正确**
2. **继续加强 transcript / memory / spill / diagnostics 这些本地运行时能力**
3. **明确拒绝 Anthropic 产品面的重中间件和远程控制栈**

换句话说，Claude Code 给 WFXM 的最大启发不是“该引入什么依赖”，而是：

**高质量 agent runtime 可以主要靠文件化状态、明确的 loop 阶段、工具预算和恢复机制来实现。**

## 8. 附：本次分析产物

- Canvas：`<cursor-project>/canvases/claude-code-deep-dive.canvas.tsx`
- 本文档：`docs/agent-analysis-2026-05/claude-code-deep-dive-2026-05.md`

