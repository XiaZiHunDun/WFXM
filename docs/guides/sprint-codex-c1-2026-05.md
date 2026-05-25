# Sprint Codex-C1（2026-05）

> C0：[sprint-codex-c0-2026-05.md](./sprint-codex-c0-2026-05.md) · 对照：[codex-butler-comparison-2026-05.md](../plans/codex-butler-comparison-2026-05.md)

## 已落地

| ID | 能力 | 模块 | 环境变量 |
|----|------|------|----------|
| C1-1 | 压缩后 steer/紧急入站 | `compaction_steer_bridge.py` + `message_queue.pop_urgent_inbound` | `BUTLER_COMPACTION_INBOUND_BRIDGE=1` |
| C1-2 | MCP 审批模板 | `mcp/approval.py` + `registry_hook` | `BUTLER_MCP_APPROVAL=1` |
| C1-3 | PermissionRequest hook | `hooks/runner` + `permissions` + `registry.dispatch` | hooks.yaml `PermissionRequest` |
| C1-4 | Goal token 预算 | `goal_loop.py` | `BUTLER_GOAL_TOKEN_BUDGET` |
| C1-5 | Tool orchestrator | `tool_orchestrator.py` → terminal/MCP | — |

## 验收

```bash
PYTHONPATH=. pytest tests/test_sprint_codex_c0.py tests/test_sprint_codex_c1.py -q
```

## MCP 审批

变更类 MCP 工具（`mutating` / `network`）会写入 `permission=mcp_tool` 待批准项；微信回复 `/批准一次` 或 `/始终允许 mcp_tool`。

## C2

已迁移至 [sprint-codex-c2-2026-05.md](./sprint-codex-c2-2026-05.md)。
