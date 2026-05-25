# Oh-My-OpenAgent 对标学习规划（Butler v4）

> **状态**：OMO-P0–P2 已落地（2026-05）  
> **源码**：[reference/oh-my-openagent](../../reference/oh-my-openagent)（gitignore，本地对照）  
> **原则**：只借鉴 Harness 层设计，不嵌入 OpenCode / OMO 运行时、零新依赖  
> **索引**：[README.md](README.md)

---

## 1. 边界

| 做 | 不做 |
|----|------|
| 压缩后 tool_use/tool_result 配对修复 | 安装 `oh-my-opencode`、54+ OpenCode hooks |
| 压缩检查点、待办空闲续跑 | Team Mode、tmux、11 Agent 人设 |
| 委派类别表、魔法词、空委派检测 | OMO `src/openclaw/` Discord/Telegram 出站 |
| 规则 walk-up、goal loop（默认关） | Hashline 默认全开（与 read_state 并存） |

与 [OpenClaw](openclaw-learning-plan-2026-05.md)、[OpenCode](opencode-learning-plan-2026-05.md) 线束去重：前置压缩、工具环、delegate_yield 等已覆盖，本计划补 **压缩存活** 与 **Harness 可观测**。

---

## 2. Butler 映射（已落地）

| 项 | 模块 | 配置 / 命令 |
|----|------|-------------|
| OMO-P0 tool-pair 修复 | `butler/core/tool_pair_repair.py` | `BUTLER_TOOL_PAIR_REPAIR=1`（默认开） |
| OMO-P0 压缩检查点 | `butler/core/compaction_checkpoint.py` | `~/.butler/sessions/<key>/compact_checkpoint.json` |
| OMO-P0 待办续跑 | `butler/core/todo_continuation.py` | `BUTLER_TODO_CONTINUATION=1`，`BUTLER_TODO_CONTINUATION_MAX=2` |
| OMO-P1 委派类别 | `butler/delegate_category_resolver.py` | `butler/delegate_categories.yaml` |
| OMO-P1 魔法词 | `butler/core/intent_keywords.py` | `BUTLER_INTENT_KEYWORDS` |
| OMO-P1 空委派 | `delegate_task` 返回 `DELEGATE_EMPTY_RESPONSE` | — |
| OMO-P1b Hashline | `butler/core/hashline.py` | `BUTLER_HASHLINE_READ=1` |
| OMO-P2 规则引擎 | `butler/core/rules_engine.py` | `BUTLER_RULES_MAX_CHARS` |
| OMO-P2 目标循环 | `butler/core/goal_loop.py` | `BUTLER_GOAL_LOOP=0`；`/循环` `/停止循环` |
| 诊断 | `butler/ops/harness_diagnostics.py` | `/诊断` |

---

## 3. OMO 源码索引

| 能力 | 路径 |
|------|------|
| Tool-pair | `src/hooks/tool-pair-validator/hook.ts` |
| Compaction checkpoint | `src/hooks/compaction-context-injector/` |
| Todo continuation | `src/hooks/todo-continuation-enforcer/` |
| Delegate category | `src/tools/delegate-task/` |
| Keyword detector | `src/hooks/keyword-detector/` |
| Hashline | `packages/hashline-core/src/` |
| Rules engine | `packages/rules-engine/src/` |
| Ralph loop | `src/hooks/ralph-loop/` |

---

## 4. 决策

| # | 预设 |
|---|------|
| D1 | 不嵌入 OMO / OpenCode 运行时 |
| D2 | todo continuation 默认开，每 turn 最多 2 次 |
| D3 | goal_loop 默认关，仅 Owner `/循环` |
| D4 | hashline 默认关，与 read_state 并存 |

---

*对照完成：2026-05*
