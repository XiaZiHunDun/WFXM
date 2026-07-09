# 普通试点项目 · 运营说明

## 用途

- 多项目 `/切换` 与 `butler projects` 冒烟
- **第二条 software 试点**：Owner 飞轮（委派 → runtime test → 摘要）见 [`pilot-flywheel.md`](pilot-flywheel.md)
- Runtime：`pilot-heartbeat`、`test-unit-smoke`（pytest 子集）
- **不含** `novel-factory`；小说工厂请用 **灵文1号**

## 微信验收（约 5 分钟）

1. `/切换 普通试点项目`
2. `/状态` — 应显示健康概览 + 当前项目
3. `/简报` — 含健康灯 + 收件箱
4. `/诊断` — Owner 简要；运维 `/诊断 详细`
5. `/项目 体检` — 无 FAIL
6. `/运行 pilot-heartbeat`
7. `/运行 test-unit-smoke`（或 CLI：`butler runtime run test-unit-smoke --project 普通试点项目 --force --no-notify`）

## 飞轮验收（约 15 分钟，P1）

见 [`pilot-flywheel.md`](pilot-flywheel.md) — 委派 dev 改 README + `/详细` + runtime smoke。

## CLI

```bash
butler project preflight --project 普通试点项目
bash scripts/butler-demo-pilot-smoke.sh
bash scripts/butler-pilot-dev-testing.sh              # 推荐：试点开发全门禁
bash scripts/butler-dev-live-flywheel-checklist.sh --probe
```

## 相关

- [`docs/guides/pilot-project-dev-testing.md`](../../../docs/guides/pilot-project-dev-testing.md) — **试点开发测试 SSOT**（含 Agent 改盘说明）

- [`../README.md`](../README.md)
- [`docs/guides/project-onboarding.md`](../../../docs/guides/project-onboarding.md)
