# `/health`·`/诊断` 格式化抽取（D0b — 2026-05-22）

> **状态**：已完成  
> **深度分析**：[`p3-deferred-deep-dive-2026-05.md`](../archive/p3-deferred-deep-dive-2026-05.md) §2

---

## 1. 目标

将 `ButlerMessageHandler._format_health_summary` 三分支重复逻辑抽到 `butler/ops/health_report.py`，**不改变** 行序、标签文案与字段语义。

---

## 2. 结构

| 模块 | 职责 |
|------|------|
| `collect_mem_stats_for_health` | 合并 health 快照与 `collect_memory_layer_stats` |
| `_shared_diagnostic_lines` | 记忆层 + 项目元数据 + runtime + model + ops |
| `_turn_diagnostic_lines` | 有轮次快照时的压缩/Schema/Skill/同步行 |
| `build_health_report` | 三分支编排 + 工具审计尾 |

`message_handler._format_health_summary` 瘦身为组装 `HealthReportInput` 并调用 `build_health_report`。

---

## 3. 验收

- 现有 `tests/test_gateway_handler.py` health 相关用例全部通过
- `pytest` 全仓绿；`butler-smoke.sh --tier=standard` 绿

---

## 4. 执行记录

| 日期 | 说明 |
|------|------|
| 2026-05-22 | 抽取 `health_report.py`，handler 委托；pytest 1105 + standard smoke 全绿 |
