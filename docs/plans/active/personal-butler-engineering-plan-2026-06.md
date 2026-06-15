# 顶级个人管家 — 工程补强计划（2026-06）

> **状态**：✅ 已结案（Phase 0–4 + 真机补验 2026-06-15）  
> **后续**：B9 运维提质 · 可选 Backlog（H2/MCP/晨间推送）见文末  
> **边界**：[`roadmap-backlog-and-boundaries-2026-05.md`](decisions/roadmap-backlog-and-boundaries-2026-05.md)

## 目标

补齐「会话不丢、回忆不编、路径不错、运维可观测」四条工程短板，再迭代主动管家面（简报/Inbox）与外联。

## 阶段

| 阶段 | 周期 | 主线 | 状态 |
|------|------|------|------|
| **0** | 1–2 周 | WS-A 会话真相 + WS-B 路径锚定 | ✅ |
| **1** | 3–4 周 | WS-C 经验污染 + WS-D 压缩可感知 + P_r | ✅ |
| **2** | 5–7 周 | WS-E 简报/Inbox + WS-F 工具叙事 | ✅ |
| **3** | 8–10 周 | WS-G 薄 MCP + B9 提质 | ✅ |
| **4** | 11–12 周 | WS-H 信任抛光 | ✅ |

## 后续（Phase 0–4 之后）

| 优先级 | 任务 | 入口 |
|--------|------|------|
| P0 运维 | B9 周循环 + 生产失败晋升 | `bash scripts/butler-b9-weekly-learning.sh` |
| P0 运维 | 委派失败复盘 / promote | `butler-delegate-failure-review.sh` · `butler-delegate-failure-promote.sh` |
| P1 真机 | 普通对话后 `/记忆来源`；opt-in 摘要行 | `BUTLER_TURN_SUMMARY_LINE=1` |
| P1 守门 | Owner 面 pytest | `bash scripts/butler-owner-inbox-smoke.sh` |
| P2 Backlog | ~~secrets Fernet~~ · ~~晨间 `/简报` cron~~ · MCP 只读模板 | 见下文「后续交付 2026-06-15」 |

## 后续交付（2026-06-15）

| 项 | 路径 / 命令 |
|----|-------------|
| B9 队列 scaffold | `B9L_prod_task_6d5304648da4` in `b9_prod_shaped_tasks.py` |
| MCP 只读模板 | `fetch-readonly` in `registry/catalog/mcp/servers.yaml` |
| 晨间简报 | `butler/ops/morning_brief_push.py` · `install-butler-morning-brief-timer.sh` |

## Phase 0 已交付

| 模块 | 路径 |
|------|------|
| read_file 路径索引 | `butler/core/session_tool_index.py` |
| 回忆 intent 横幅 | `butler/core/session_recall_intent.py` |
| Loop 冷启动 hydrate | `butler/core/session_hydration.py` |
| 工作区锚定 | `butler/tools/path_safety.py` |
| 网关接线 | `message_handler.py`、`locked_phases.py` |
| 斜杠命令 | `/本轮已读`、`/本轮工具` |
| tool_audit 持久化 | `butler/tools/tool_audit.py` |
| `/诊断` 工具工作区行 | `butler/ops/health_report.py` |
| 测试 | `tests/test_session_continuity.py` |

### 验收（真机）

1. `/new` → 读 5 docs → 重启网关 → 再问清单 → 仅 5 条 `read_file` 路径  
2. `/诊断` 见 `工具工作区: .../LingWen1`  
3. `/本轮已读` 与清单回答一致  

### 环境变量

见 `docs/config/reference.md`：`BUTLER_SESSION_HYDRATE`、`BUTLER_WORKSPACE_ANCHOR_STRICT` 等。

## Phase 1 已交付

| 模块 | 路径 |
|------|------|
| recall intent 跳过 experience/skill 预取 | `memory_prefetch.py`、`skills/injection_policy.py` |
| P_r 回合结束引用估算 | `memory/prefetch_retrieval_metrics.py`、`locked_phases.py` |
| `/压缩报告` | `compaction_status.py`、`info_commands.py` |
| `/诊断` P_r 行 | `memory/metrics_persist.py` |
| 测试 | `tests/test_phase1_recall_compaction.py` |

### 验收（真机）

1. 问「列清单」→ 用户消息**无** `## 相关知识（Butler Skill）` 前缀（或 experience 块）
2. `/压缩报告` → 显示压缩状态 + 检查点摘要（若曾压缩）
3. `/诊断` → 记忆效果度量含 `P_r 预取引用率`（有预取轮次后）

### 真机验收（2026-06-15 17:14）

1. `/new` → 空清单 ✅  
2. 读 `docs/` 5 个 LingWen1 真文档 ✅（非 `projects/docs` 夹具）  
3. 清单与 `/本轮已读` 一致（5 条）✅  

## Phase 2 已交付

| 模块 | 路径 |
|------|------|
| 管家简报 / 收件箱 | `butler/ops/butler_inbox.py` |
| 工具叙事 | `butler/core/tool_narrative.py` |
| 斜杠命令 | `/简报` `/inbox`；`/本轮工具` 叙事化（`raw` 保留原始） |
| 测试 | `tests/test_phase2_brief_narrative.py` |

### 验收（真机）

1. `/简报` → 显示当前项目 + 待办/提醒/待审汇总  
2. `/inbox` → 分项列出待办样本、提醒、门控、本轮已读数  
3. 读文件后 `/本轮工具` → 中文叙事（如「读取 docs/README.md」）；`/本轮工具 raw` → 原始 JSON 预览  

### 真机验收（2026-06-15 17:24）

1. `/简报` `/inbox` `/本轮工具` ✅  

## Phase 3 已交付

| 模块 | 路径 |
|------|------|
| MCP + B9 主人可观测 | `butler/ops/owner_quality_surface.py` |
| 简报/Inbox 接线 | `butler/ops/butler_inbox.py`（MCP 行 + 委派质量行） |
| 斜杠命令 | `/委派质量`（别名 `/b9`） |
| 测试 | `tests/test_phase3_owner_quality.py` |

### 验收（真机）

1. `/简报` → 含 `MCP:` 与 `委派质量:` 行  
2. `/inbox` → 含 `## MCP` 与 `## 委派质量` 节  
3. `/委派质量` → B9 基准 + 生产失败分类 + 周趋势（有快照时）  

### 真机验收（2026-06-15 17:33）

1. `/简报` `/inbox` `/委派质量` ✅  

## Phase 4 已交付

| 模块 | 路径 |
|------|------|
| 操作摘要行 H1 | `butler/core/turn_summary_line.py` |
| 记忆来源 H3 | `butler/core/memory_source_surface.py` |
| 纠正意图 H4 | `butler/core/correction_intent.py` |
| 信任主人面 | `butler/ops/owner_trust_surface.py` |
| 简报/Inbox 接线 | `butler/ops/butler_inbox.py`（信任行 + inbox 节） |
| 斜杠命令 | `/信任` `/记忆来源` |
| 环境变量 | `BUTLER_TURN_SUMMARY_LINE`（opt-in 长回复前摘要） |
| 测试 | `tests/test_phase4_owner_trust.py` |

### 验收（真机）

1. `/信任` → Skill 模式、权限缓存、边界 warn、记忆来源一行  
2. `/记忆来源` → 上轮预取命中节选（脱敏）  
3. `/简报` → 含 `信任:` 行  
4. 「刚才那句不对：…」→ 自动写入 correction 经验（不经 LLM）  
5. （opt-in）`BUTLER_TURN_SUMMARY_LINE=1` 时长回复前附 `📎 读了N文件·…`  

### 真机验收（2026-06-15 17:47）

1. `/信任` `/记忆来源` `/简报` `/inbox` ✅  
2. 纠正句 → `owner_experience` id=238 ✅  
3. `/记忆来源` 空：本轮仅斜杠命令、无 LLM 预取轮次 — **符合预期**  

### 真机补验（建议）

1. 发一句普通任务（如「用一句话总结 LingWen1 的 README」）→ `/记忆来源` 应有经验/项目命中  
2. `.env` 设 `BUTLER_TURN_SUMMARY_LINE=1` 后 `butler-gateway-ops.sh restart` → 长回复前应出现 `📎 读了N文件·…`  

### 真机补验（2026-06-15 18:24–18:28）✅

| 步骤 | 结果 |
|------|------|
| 普通对话总结 README | ✅ 正确摘要；首条附会话恢复提示（冷启动预期） |
| `/记忆来源` | ✅ 预取 2604 字符 · 经验 4 · 项目检索 1 · Skill fallback/experience_hit_with_ref · 脱敏节选 8 条 |
| 读 docs + 长总结 | ✅ 回复前 `📎 读了19文件·检索1次·无委派`（`BUTLER_TURN_SUMMARY_LINE=1`） |

**备注**：P_r 0/10 表示预取块未在回复字面重叠（摘要型回答常见）；非功能缺陷。

## 守门

```bash
bash scripts/butler-owner-inbox-smoke.sh
bash scripts/butler-context-compaction-smoke.sh
bash scripts/butler-five-reports-gate.sh
```

## 历史待办（已清空）

- ~~Phase 0–4 全部 WS 主线~~
