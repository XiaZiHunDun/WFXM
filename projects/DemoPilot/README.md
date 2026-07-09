# 普通试点项目（Butler 第二项目模板）

- **Butler 名称**：`普通试点项目`（微信 `/切换 普通试点项目`）
- **用途**：多项目切换、runtime 列表/到期扫描冒烟；**不含** `novel-factory/`
- **Runtime**：`runtime/jobs.yaml` 仅 `pilot-heartbeat`（默认不推微信）

```bash
butler project preflight --project 普通试点项目
butler runtime list --project 普通试点项目
butler runtime run pilot-heartbeat --project 普通试点项目
butler runtime run test-unit-smoke --project 普通试点项目 --force --no-notify
bash scripts/butler-demo-pilot-smoke.sh
```

- **lifecycle**: `active`（非厂长项目）
- **Owner 飞轮**: [`docs/pilot-flywheel.md`](docs/pilot-flywheel.md)（P1 第二条 software 试点）
- **运营说明**: [`docs/pilot-setup.md`](docs/pilot-setup.md)
- **开发测试**: [`docs/guides/pilot-project-dev-testing.md`](../../docs/guides/pilot-project-dev-testing.md)

完整小说工厂能力请使用 **灵文1号**（`projects/LingWen1/`）。
