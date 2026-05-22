# 演示试点（Butler 第二项目模板）

- **Butler 名称**：`演示试点`（微信 `/切换 演示试点`）
- **用途**：多项目切换、runtime 列表/到期扫描冒烟；**不含** `novel-factory/`
- **Runtime**：`runtime/jobs.yaml` 仅 `pilot-heartbeat`（默认不推微信）

```bash
butler runtime list --project 演示试点
butler runtime run pilot-heartbeat --project 演示试点
```

完整小说工厂能力请使用 **灵文1号**（`projects/LingWen1/`）。
