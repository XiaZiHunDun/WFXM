# @butler/infrastructure — 已归档模块

以下 stub **不在生产调用链**（生产用 `packages/adapters` + `packages/persistence`）。

| 模块 | 路径 | 状态 |
|------|------|------|
| `llm` | `_archive/llm/` | 已归档；生产 LLM 在 `packages/adapters/src/llm/` |
| `wechat` | `_archive/wechat/` | 已归档；生产微信在 `packages/adapters/src/wechat/` |

`layers.ts` 仍从 `_archive` 引用上述 stub 以维持 Effect Layer 组合示例；**禁止** `apps/*` 或 `runtime` 导入。

仍活跃：guards、persistence（并行 schema，勿接生产）、mcp 参考、migration、acl 实验。
