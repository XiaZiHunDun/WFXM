# 演示试点（Butler 第二项目模板）

- **Butler 名称**：`演示试点`（微信 `/切换 演示试点`）
- **用途**：多项目切换、runtime 列表/到期扫描冒烟；**不含** `novel-factory/`
- **Runtime**：`runtime/jobs.yaml` 仅 `pilot-heartbeat`（默认不推微信）

```bash
butler project preflight --project 演示试点
butler runtime list --project 演示试点
butler runtime run pilot-heartbeat --project 演示试点
butler runtime run test-unit-smoke --project 演示试点 --force --no-notify
bash scripts/butler-demo-pilot-smoke.sh
```

- **lifecycle**: `active`（非厂长项目）
- **运营说明**: [`docs/pilot-setup.md`](docs/pilot-setup.md)

完整小说工厂能力请使用 **灵文1号**（`projects/LingWen1/`）。
