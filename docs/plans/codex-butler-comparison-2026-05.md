# Codex ↔ Butler 全量对照（2026-05）

> 源码：`reference/codex/codex-rs` · 落地：`butler/` · 原则：零新增 pip、不移植 Rust/OS 沙箱

## 架构对照

| Codex | Butler | 关系 |
|-------|--------|------|
| `session/turn.rs` | `core/agent_loop.py` | Turn 循环（模式对齐） |
| `compact.rs` | `context_compressor.py` + `compaction_task.py` | 压缩 + C0-1 相位 |
| `tools/orchestrator.rs` | `core/tool_orchestrator.py` | C1-5 子集（terminal/MCP gate） |
| `execpolicy/` | `butler/execpolicy/` | C0-2 YAML 子集 |
| `command_canonicalization.rs` | `tools/command_canonicalize.py` | C0-3 |
| `guardian/` | `core/auto_review.py` | C0-4 极简子集 |
| `mcp_tool_call.rs` | `mcp/approval.py` + `mcp/manager.py` | C1-2 |
| `input_queue.rs` | `compaction_steer_bridge` + `message_queue` + `steer` | C1-1 |

## Sprint Codex-C0（已落地）

| ID | 能力 | 模块 | 默认 |
|----|------|------|------|
| C0-3 | 审批命令归一化 | `butler/tools/command_canonicalize.py` | 开 |
| C0-1 | mid-turn 压缩相位 | `butler/core/compaction_phase.py` | 开 |
| C0-2 | prefix_rule 策略 | `butler/execpolicy/` | 开 |
| C0-4 | 自动审批 reviewer | `butler/core/auto_review.py` | **关** |

验收：`pytest tests/test_sprint_codex_c0.py -q`

## Sprint Codex-C1（已落地）

| ID | 能力 | 模块 |
|----|------|------|
| C1-1 | 压缩后 steer / 紧急入站 | `compaction_steer_bridge.py` |
| C1-2 | MCP 审批模板 | `mcp/approval.py` |
| C1-3 | PermissionRequest hook | `hooks/runner.py` |
| C1-4 | Goal token 预算 | `goal_loop.py` |
| C1-5 | Tool orchestrator | `tool_orchestrator.py` |

验收：`pytest tests/test_sprint_codex_c0.py tests/test_sprint_codex_c1.py -q`  
指南：[sprint-codex-c1-2026-05.md](../guides/sprint-codex-c1-2026-05.md)

## Sprint Codex-C2（已落地）

| ID | 能力 | 模块 | 默认 |
|----|------|------|------|
| C2-1 | Provider remote compact | `remote_compact.py` → `context_compressor` | **关** |
| C2-2 | Transcript → 记忆提炼 | `memory/transcript_memory_pipeline.py` | **关** |
| C2-3 | 第 N 条 user fork | `transcript_fork.py` | 开（owner 命令） |
| C2-4 | thread_item 出站事件 | `gateway/item_events.py` | 开 |

验收：`pytest tests/test_sprint_codex_c0.py tests/test_sprint_codex_c1.py tests/test_sprint_codex_c2.py -q`  
指南：[sprint-codex-c2-2026-05.md](../guides/sprint-codex-c2-2026-05.md)

## 明确不做

Rust 运行时重写、linux-sandbox/Seatbelt、`codex mcp-server` Host、V8 code-mode、全量 SQLite state DB、network deferred approval、Guardian 完整克隆。

## 与 CC / 四报告 Sprint 正交

- **CC 线束**：压缩/prune/队列已覆盖；Codex 增量为 execpolicy + canonical + mid-turn injection。
- **Sprint A–D**：网关幂等、Handoff、MCP profiles 已落地；与 Codex 无冲突。
