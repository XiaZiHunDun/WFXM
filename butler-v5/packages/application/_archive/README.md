# @butler/application — 已归档模块

以下模块**不在生产调用链**（生产 Loop 在 `packages/runtime` + `apps/api/wechat-inbound-butler`）。

| 模块 | 路径 | 状态 |
|------|------|------|
| `delegate-task` | `_archive/delegate-task/` | 已归档；生产委派见 `delegate-runtime.ts` |
| `run-workflow` | `_archive/run-workflow/` | 已归档；非产品 Workflow DAG |
| `dream` | `_archive/dream/` | 已归档；百轮记忆未立项 |

仍活跃（Effect 脚手架 / 包内测试）：

- `run-loop` — 冻结参考，勿声称已交付产品能力。
