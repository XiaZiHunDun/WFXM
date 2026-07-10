# 灵文1号 · 面试演示改进项清单（2026-07-09）

> 微信发「列出灵文1号的改进项」或「架构分析」时，莎丽可读此文件 + `MEMORY.md` + `/项目待办`。

## P0 — 演示前优先

| # | 改进项 | 说明 | 状态 |
|---|--------|------|------|
| 1 | Agent JSON schema 校验 | novel-factory 灵感/作家/审核 Agent 输出缺统一校验，维护期易 silent fail | 进行中 |
| 2 | workflow_state 微信口径 | `/工作流` 与 `factory-status-daily` runtime 摘要字段应对齐 | ✅ 已实现（6703cec）`/工作流 list` 前置 4 字段与 `builtin:workflow_state_digest` 一致 |
| 3 | 验收文档日期卫生 | `owner-sim-smoke.md` 日期与 MEMORY Notes 不一致 | 待做 |
| 3a | 测试残留目录清理 | 根 `MagicMock/`、`projects/LingWen1/MagicMock/`、`projects/exists/`、`projects/new-project/` 均为 pytest mock 泄漏；演示前宜删 | ✅ 已清（2026-07-10） |

## P1 — 架构与 Butler 集成

| # | 改进项 | 说明 | 状态 |
|---|--------|------|------|
| 4 | content vs dev 委派边界 | content 只碰 `docs/`；dev 改代码须走 safe_root + owner 验收 | 已约定 |
| 5 | runtime jobs 可见性 | `runtime/jobs.yaml` 已注册 7 个 job，微信端缺一览命令 | ✅ 已实现（Sprint 3）`/定时` 或 `/runtime`/`/定时任务` 返回 7 jobs + schedule/last/next run |
| 6 | 记忆 Pending 去重 | fact 提取重复写入 Decisions（验收日三条） | ✅ 已实现：formal bullet 按 section+content 精确去重；Pending approve/approve_all 覆盖 |
| 7 | 项目待办与 MEMORY 联动 | `/项目待办` 持久盘 vs MEMORY Pending 应定期对齐 | 待做 |

## P2 — 维护态 backlog

| # | 改进项 | 说明 | 状态 |
|---|--------|------|------|
| 8 | 旧 sprint 测试迁入域目录 | 见 `consolidation-audit-2026-06-23.md` 阶段 3 | 低优先级 |
| 9 | consistency 报告结构化 | 周报全文过长，需固定摘要模板供微信通知 | 待做 |
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
- 整理审计：`docs/consolidation-audit-2026-06-23.md`
