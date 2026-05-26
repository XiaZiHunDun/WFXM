# Butler 包

Butler v4 产品代码：自建 **Agent Loop** + 分层记忆 + Skill + Gateway 集成。

- 架构：[`../docs/architecture/v4-architecture.md`](../docs/architecture/v4-architecture.md)
- 设计：[`../docs/design/design.md`](../docs/design/design.md)
- CC 对照：[`../docs/plans/active/cc-butler-gap-analysis-2026-05.md`](../docs/plans/active/cc-butler-gap-analysis-2026-05.md)
- 配置：[`../docs/config/reference.md`](../docs/config/reference.md)
- 入口：`python -m butler.main` 或控制台命令 `butler`

## 子目录

| 目录 | 职责 |
|------|------|
| `core/` | Loop 编排：`agent_loop`、`context_pipeline`、`llm_retry`、`tool_batch`、`parallel_tools`；P0–P2：`tool_result_storage`、`tool_prune_policy`、`read_state`、`streaming_tools`、`cache_safe_delegate`、`turn_token_budget` |
| `transport/` | LLM 客户端、流式 `on_tool_call_ready`、Provider、failover |
| `gateway/` | `message_handler`、`message_queue`、`outbound_bridge`、`session_registry`、微信 iLink |
| `tools/` | 工具注册、JSON envelope、委派、`read_state` 校验 |
| `memory/`, `skills/` | 记忆与 Skill |
| `hooks/` | Shell hooks（CC 协议）示例与 runner |
| `cli/` | CLI 展示与流式输出 |

微信生产部署：[`../docs/guides/wechat-gateway-ops.md`](../docs/guides/wechat-gateway-ops.md)  
发版抽测 H1–H10：[`../docs/guides/wechat-daily-smoke-checklist.md`](../docs/guides/wechat-daily-smoke-checklist.md)
