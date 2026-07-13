# 灵文1号 · 面试演示改进项清单（2026-07-09）

> 微信发「列出灵文1号的改进项」或「架构分析」时，莎丽可读此文件 + `MEMORY.md` + `/项目待办`。

## P0 — 演示前优先

| # | 改进项 | 说明 | 状态 |
|---|--------|------|------|
| 1 | Agent JSON schema 校验 | novel-factory 灵感/作家/审核 Agent 输出缺统一校验，维护期易 silent fail | ✅ 已实现：3 schema（base_layer/writer_chapter/reviewer_report）+ 3 validator + 共享基类 `_base.py` + dispatcher `validate_all.py`（writer/reviewer/inspiration 三 suite）；LingWen1 ch001.md + ch001_审核员A_审核.md + 基础层模板 全部 0 错误 |
| 2 | workflow_state 微信口径 | `/工作流` 与 `factory-status-daily` runtime 摘要字段应对齐 | ✅ 已实现（6703cec）`/工作流 list` 前置 4 字段与 `builtin:workflow_state_digest` 一致 |
| 3 | 验收文档日期卫生 | `owner-sim-smoke.md` 日期与 MEMORY Notes 不一致 | ✅ 已清（2026-07-11）MEMORY Notes 删 3 条已实现 Pending（#2/#5/#6），新增卫生留痕；owner-sim-smoke-{date}.md 本就 gitignore 且 sim 每次重写 |
| 3a | 测试残留目录清理 | 根 `MagicMock/`、`projects/LingWen1/MagicMock/`、`projects/exists/`、`projects/new-project/` 均为 pytest mock 泄漏；演示前宜删 | ✅ 已清（2026-07-10） |

## P1 — 架构与 Butler 集成

| # | 改进项 | 说明 | 状态 |
|---|--------|------|------|
| 4 | content vs dev 委派边界 | content 只碰 `docs/`；dev 改代码须走 safe_root + owner 验收 | ✅ 已硬化：`butler.hooks.delegation_boundary_hook`（deny 优先 ACL）+ `scripts/butler-delegation-boundary-smoke.sh`（4 case ALL PASS）+ `projects/LingWen1/config/hooks.yaml` 注册 PreToolUse + `projects/LingWen1/config/permissions.yaml` delegation 段。10 单测 + smoke 双轨；role 缺失静默放行；新项目无 delegation 段 fail-open + WARN |
| 5 | runtime jobs 可见性 | `runtime/jobs.yaml` 已注册 7 个 job，微信端缺一览命令 | ✅ 已实现（Sprint 3）`/定时` 或 `/runtime`/`/定时任务` 返回 7 jobs + schedule/last/next run |
| 6 | 记忆 Pending 去重 | fact 提取重复写入 Decisions（验收日三条） | ✅ 已实现：formal bullet 按 section+content 精确去重；Pending approve/approve_all 覆盖 |
| 7 | 项目待办与 MEMORY 联动 | `/项目待办` 持久盘 vs MEMORY Pending 应定期对齐 | ✅ 已实现（每日 06:00 UTC `todos-pending-drift-daily`，只读漂移报告推送微信） |

## P2 — 维护态 backlog

| # | 改进项 | 说明 | 状态 |
|---|--------|------|------|
| 8 | 旧 sprint 测试迁入域目录 | 见 `consolidation-audit-2026-06-23.md` 阶段 3 | ✅ 已完成：106 个 sprint 测试全量迁出 tests/ 根目录 → tests/{gateway:36, tools:29, core:18, runtime:8, transport:2, ops:2, hooks:2, memory:1, io:1}。conftest.py auto-marker 自然失效（无 root test_sprint*），pyproject 标记描述更新。**2026-07-11 续**：drift fail 已修，commit `323862e fix(tests): repair sprint migration drift failures`（9 drift fix + 99 旧测试删除 + 1 SQL bug + 1 croniter 兼容 + 1 _CONN_PATH 隔离）。tools/ops/runtime/hooks 四域 676 passed；gateway 63 fail 为预存在（P2 之外） |
| 9 | consistency 报告结构化 | 周报全文过长，需固定摘要模板供微信通知 | ✅ 已实现（每周一 09:30 UTC `consistency-summary-weekly`，从 JSON 提炼 P0/P1/P2 + 5 子检查计数 + top 5 P1 详情 + verdict + 陈旧标；原 `consistency-weekly` 长报告保留） |
| 10 | publish mutating job 审批流 | `publish-archive` / `publish-merge` 默认关，演示时口头说明即可 | 已配置 |

## 已完成（演示可点名）

- [x] owner-demo sim manifest + D08（content 文档）/ D08-dev（dev 代码）委派脚本
- [x] 个人管家默认 + 环境级 tool scope（`BUTLER_BIND_DEFAULT_PROJECT=0`）
- [x] P0 记忆工具接通（2026-05-21 首轮微信验收）
- [x] novel-factory 25 步主流程跑完，workflow_state 进入维护态（PHASE_COMPLETE）

## 关联文件

- 项目待办：`.butler/todos.json`（发 `/项目待办`）
- 委派任务：`~/.butler/runtime/tasks/`（发 `/任务`）
- Runtime 注册：`runtime/jobs.yaml`
- 漂移报告 collector：`butler/tools/project_todos_drift_ops.py`
- consistency 摘要 collector：`butler/tools/consistency_summary_ops.py`
- Agent schema 校验：`projects/LingWen1/novel-factory/tools/validators/`（_base.py + 3 schema + 3 validator + dispatcher）
- 整理审计：`docs/consolidation-audit-2026-06-23.md`
