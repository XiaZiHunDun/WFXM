# 第二轮熵减方案（P3 — 实现细节）

> **状态**：**已完成**（2026-05-22）  
> **前置**：[`consolidation-2026-05.md`](consolidation-2026-05.md) P0–P2 已完成；[`post-consolidation-roadmap-2026-05.md`](post-consolidation-roadmap-2026-05.md)  
> **原则**：不改 Agent Loop / 微信主路径语义；每批结束 `bash scripts/butler-smoke.sh --tier=full`  
> **不动**：`reference/`、`novel-factory/` 领域脚本

---

## 1. 目标

消化 v4 迁型后的**实现层熵**：死代码、空 Hook、未接线 Profile 字段、pyproject 虚胖、网关命令不一致、重复 env/Owner 解析。

---

## 2. 分批执行

### P3a — 安全删除（零行为变更）

| ID | 任务 | 验收 |
|----|------|------|
| a1 | 删 `butler/core/iteration_budget.py` | 无 import |
| a2 | 删 `workflows/hooks.py` 注册与 `orchestrator` 空 Hook 调用 | 灵文 Lead 仍靠 system prompt |
| a3 | 删 `_pre_llm_lingwen_lead`、`_on_project_switched` 死 Hook | 同上 |
| a4 | 删 `hermes_home_display` / `resolve_hermes_home` | config/paths 无残留 |
| a5 | 删 `_is_global_session_command` + 测试改用 sessionless | pytest |
| a6 | 删 `BUTLER_GATEWAY_ACTIVE` 写入与测试断言 | pytest |
| a7 | `pyproject.toml` 移除 `fire` 与未用 optional extras | `pip install -e ".[wechat]"` |
| a8 | `AgentProfile` 移除未使用的 `toolsets` / `max_iterations` | 仅保留 system_prompt |
| a9 | 清理未使用 import（main、message_handler） | ruff/测试 |
| a10 | `.env.example` 移除 `WECHATY_PUPPET*`；补常用 env 注释 | 文档 |

### P3b — 行为对齐（小改进）

| ID | 任务 | 验收 |
|----|------|------|
| b1 | `_is_sessionless_command` 增加 `/批准`、`/开发状态`、`/开发验收` 等 | 长对话中可立即响应 |
| b2 | `cli/slash_commands.py` 增加 `/工作流`、`/workflow` | Tab 补全一致 |
| b3 | 更新 `hermes-extraction-map` 中 iteration_budget 行 | 文档 |

### P3c — 结构合并

| ID | 任务 | 验收 |
|----|------|------|
| c1 | `butler/env_parse.py` 统一 env 布尔解析 | 4 处调用改 import |
| c2 | `owner_gate.resolve_owner_wechat_chat_id()`；`notify` 复用 | 单点 |
| c3 | `project_preflight.resolve_tool_safe_root()`；main/gateway 复用 | 无重复片段 |
| c4 | `memory_plugin` 文档去 Hermes Provider 口吻（不改行为） | 注释 only |

**本轮不做**（深度分析见 [`p3-deferred-deep-dive-2026-05.md`](p3-deferred-deep-dive-2026-05.md)）：记忆双轨合并、`/health` 三分支大重构、微信 `/steer`（保留 CLI only）。

---

## 3. 验收

```bash
PYTHONPATH=. pytest -q
bash scripts/butler-smoke.sh --tier=full
```

---

## 4. 执行记录

| 日期 | 批次 | 说明 |
|------|------|------|
| 2026-05-22 | 方案 | 本文档 |
| 2026-05-22 | P3a–c | 死代码/依赖/Hook/Profile；sessionless 对齐；env_parse、owner、safe_root；1092 pytest + full smoke |

### 交付清单

- [x] P3a 安全删除
- [x] P3b 行为对齐
- [x] P3c 结构合并（不含 memory 双轨、/health 大重构）
