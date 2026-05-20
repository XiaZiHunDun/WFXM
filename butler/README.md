# Butler 包

Butler v4 产品代码：自建 **Agent Loop** + 分层记忆 + Skill + Gateway 集成。

- 架构：[`../docs/architecture/v4-architecture.md`](../docs/architecture/v4-architecture.md)
- 设计：[`../docs/design/design.md`](../docs/design/design.md)
- 入口：`python -m butler.main` 或控制台命令 `butler`

## 子目录

| 目录 | 职责 |
|------|------|
| `core/` | Loop 编排与子模块（`agent_loop`, `tool_batch`, `llm_retry`, `context_pipeline`）|
| `transport/` | LLM 客户端与 Provider |
| `gateway/` | 入站消息、`/health`、session 生命周期 |
| `tools/` | 工具注册、JSON envelope、审计 |
| `memory/`, `skills/` | 记忆与 Skill |
| `cli/` | CLI 展示与流式输出 |

根目录 `agent/`、`gateway/`（Hermes）由 Gateway 子进程使用，非本包实现。
