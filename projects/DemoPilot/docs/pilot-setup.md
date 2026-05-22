# 演示试点 · 运营说明

## 用途

- 多项目 `/切换` 与 `butler projects` 冒烟
- Runtime：`pilot-heartbeat`、`test-unit-smoke`（pytest 子集）
- **不含** `novel-factory`；小说工厂请用 **灵文1号**

## 微信验收（约 5 分钟）

1. `/切换 演示试点`
2. `/状态` — 应显示 `lifecycle: active`、Lead: 否
3. `/项目 体检` — 无 FAIL
4. `/运行 pilot-heartbeat`
5. `/运行 test-unit-smoke`（或 CLI：`butler runtime run test-unit-smoke --project 演示试点 --force --no-notify`）

## CLI

```bash
butler project preflight --project 演示试点
bash scripts/butler-demo-pilot-smoke.sh
```

## 相关

- [`../README.md`](../README.md)
- [`docs/guides/project-onboarding.md`](../../../docs/guides/project-onboarding.md)
