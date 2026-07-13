# 普通试点项目 · 项目文档索引

> 第二条 software 试点（多项目 `/切换` + Runtime 冒烟）。
> 与 `灵文1号` 互为对照：**平台能力应在两个项目上可重复**。
> **不含** `novel-factory`；小说工厂请用 `灵文1号`。

## 项目定位

- **Butler 名称**：`普通试点项目`
- **目录**：`projects/DemoPilot/`
- **类型**：software 模板（轻量）
- **核心跑通**：多项目切换 + Runtime timer + Owner 飞轮（委派 → runtime test → 摘要验收）

## 文档

| 文档 | 用途 |
|------|------|
| [`pilot-setup.md`](pilot-setup.md) | 运营说明：用途、微信验收 5 分钟剧本、Runtime 任务清单 |
| [`pilot-flywheel.md`](pilot-flywheel.md) | Owner 飞轮（PM P1 真机）：登记 → 切换 → 委派 dev → runtime 测试 → 摘要 |
| [`pilot-log.md`](pilot-log.md) | 测试日志（与 `灵文1号/pilot-log.md` 同结构；事件流） |

## 微信验收（5 分钟剧本节选）

```
/切换 普通试点项目
/状态                          # 健康概览
/简报                          # 健康灯 + 收件箱
/诊断                          # Owner 简要
/项目 体检                     # 无 FAIL
/运行 pilot-heartbeat
/运行 test-unit-smoke
```

飞轮剧本（15 分钟，P1）见 `pilot-flywheel.md`。

## 相关

- 平台决策入口：`docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`
- Dev 能力上限：`docs/plans/decisions/dev-capability-ceiling-vs-cc-cli-2026-06.md`
- 灵文1号 README：[`../../LingWen1/docs/README.md`](../../LingWen1/docs/README.md)
- 项目根索引：[`../../README.md`](../../README.md)