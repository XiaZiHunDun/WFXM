# Reference 目录外部依赖分析

## 结论摘要

`reference/` 里真正值得 Butler 学习的主要是运行时策略、权限模型、memory 召回和 gateway 安全默认值；大多数外部依赖本身并不适合直接引入，因为它们绑定了 Rust/Bun/Effect、多通道 IM、浏览器自动化、OTEL 或 MCP Host 全家桶等与 Butler 当前边界冲突的产品形态。

核心判断是：**学模式，不搬技术栈**。

## 按产品总览

### Codex

- 定位：Rust 本地 coding agent
- 代表依赖：`tokio`、`clap`、`ratatui`、`rmcp`、`landlock`、`opentelemetry`
- 最值得借鉴：exec policy、工具门控链、薄 MCP、日志分层
- 结论：只学架构模式，不引 Rust 运行时与 OTEL/Sentry

### OpenClaw

- 定位：Node 多通道个人 AI Gateway
- 代表依赖：`@earendil-works/pi-*`、`express`、`ws`、`grammy`、`kysely`、`playwright-core`、`quickjs-wasi`
- 最值得借鉴：DM pairing、安全默认值、多账号/多 workspace 路由、model failover
- 结论：不引多通道 gateway、浏览器/Canvas 平台、默认 OTEL

### OpenCode

- 定位：Bun/Effect coding agent runtime
- 代表依赖：`effect`、`ai`、`@ai-sdk/*`、`drizzle-orm`、`@modelcontextprotocol/sdk`、`@opentui/*`
- 最值得借鉴：权限状态机、上下文经济学、子 session/委派模型
- 结论：不引 Effect、AI SDK 替换 Transport、Drizzle 全量会话库

### Hermes Agent

- 定位：Python 通用 Agent OS
- 代表依赖：`openai`、`anthropic`、`httpx`、`prompt_toolkit`、`croniter`、`exa-py`、`firecrawl-py`
- 最值得借鉴：provider hook、gateway 投递/中断、跨会话 recall、记忆生命周期
- 结论：不回退到 `AIAgent` 单体、多平台 gateway、40+ 工具平台化

### Claude-Mem

- 定位：Bun memory compression system
- 代表依赖：`@anthropic-ai/claude-agent-sdk`、`bullmq`、`ioredis`、`pg`、`express`、MCP SDK
- 最值得借鉴：三层召回、timeline anchor、observation 分层、异步摘要队列
- 结论：不引 Bun worker、Chroma MCP、Viewer/UI

### ECC

- 定位：harness-native agent OS / 治理资产包
- 代表依赖：`@iarna/toml`、`ajv`、`sql.js`
- 最值得借鉴：hook 契约、manifest 治理、iterative retrieval、continuous-learning-v2
- 结论：不引 ecc2 Rust 控制面与托管面

### Superpowers

- 定位：workflow/skill 方法论包
- 代表依赖：几乎零运行时依赖
- 最值得借鉴：workflow gate、review gate、verification before completion
- 结论：适合作为 skill 设计参考，不是依赖引入对象

## 建议吸收的方向

### 高优先级

1. Memory 召回增强  
   来源：`claude-mem`  
   吸收内容：timeline anchor、observation id、异步摘要队列  
   落地方式：继续使用现有 `semantic_index` + `aiosqlite`，不引 Bun/Chroma

2. Gateway 安全与路由  
   来源：`openclaw`  
   吸收内容：DM pairing、allowlist、安全默认值、route-to-workspace  
   落地方式：映射到微信 `session_key` / 项目路由，不扩展多通道

3. 权限与委派 UX  
   来源：`opencode`  
   吸收内容：ask once/always、子 session 状态、上下文预算  
   落地方式：落在 `human_gate`、`permissions.py`、`task_orchestrator.py`

### 中优先级

4. Provider 扩展组织  
   来源：`hermes-agent` + `openclaw`  
   吸收内容：provider profile、failover 组织方式  
   落地方式：演进 `butler/transport/providers.py`，不换 SDK 栈

5. Skills / workflow 治理  
   来源：`ECC` + `superpowers`  
   吸收内容：manifest 校验、hook 契约、iterative retrieval、verification gate  
   落地方式：继续走 Butler skill/workflow，不引 ecc2

## 明确不建议引入

- 全量 MCP Host
- 浏览器自动化平台
- OTEL 默认 APM
- Rust / Bun / Effect 重写核心
- Drizzle / SQLite 全量会话库
- Hermes `AIAgent` 单体回退
- 多通道 IM Gateway
- 桌面/托盘/Canvas 产品化

## Butler 模块级结论

### Memory

- 当前基线：`butler/memory/recall_layers.py` 已支持 `index -> timeline -> fetch`
- 最佳参考：`claude-mem`
- 继续可吸收：observation 元数据、timeline anchor 解释性、按引用 id 回拉全文 UX
- 建议边界：继续走 Python + 本地索引，不引 Bun / Chroma / MCP Host

### Gateway

- 当前基线：`butler/gateway/message_handler.py` 已有 queue mode、reply admission、bot loop guard、two-phase confirm、注入审查
- 最佳参考：`openclaw` + `hermes-agent`
- 继续可吸收：pairing/allowlist/onboarding、route-to-workspace、投递语义
- 建议边界：保持微信单网关，不扩展多通道与 browser/canvas 平台

### Workflow / Skills / Permissions

- 当前基线：`butler/task_orchestrator.py` 已有 DAG、并行、retry、rescue、approval、child session key
- 最佳参考：`opencode` + `ECC` + `superpowers`
- 继续可吸收：批准缓存、状态机解释、manifest/schema 校验、skill 触发回归
- 建议边界：沿用 Butler AgentLoop，不引 Effect / Drizzle / task server

## 最终建议

近期最值得继续深挖的是三条线：

1. `claude-mem` 的 memory 分层召回
2. `openclaw` 的 gateway 安全默认值与路由
3. `opencode` / `ECC` / `superpowers` 的权限与 workflow 治理

最稳妥的总体策略仍然是：**提炼机制，保留 Python + 微信单网关 + 薄 MCP 主线**。
