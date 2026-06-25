# 演示试点 · Owner 飞轮（第二条 software 试点）

> **目的**：在 **非灵文** 的轻量 software 项目上，走通 PM P1 主路径：  
> **登记 → 切换 → 委派 dev → runtime 测试 → 摘要验收**  
> **SSOT**：[`dev-capability-ceiling-vs-cc-cli-2026-06.md`](../../../docs/plans/decisions/dev-capability-ceiling-vs-cc-cli-2026-06.md) §P1 真机飞轮

---

## 1. 为什么用「演示试点」

| 对比 | 灵文1号 | 演示试点 |
|------|---------|----------|
| 类型 | Lead + novel-factory | software 模板 |
| 用途 | 平台真机 + 厂长剧本 | **第二条 vertical**、多项目切换 |
| 复杂度 | 高（业务 Skill、章节） | 低（README + runtime 冒烟） |

Butler 平台能力应在 **两个项目** 上可重复，而不是只围着灵文验收。

---

## 2. 前置（一次性）

```bash
cd /path/to/WFXM
butler project preflight --project 演示试点
bash scripts/butler-demo-pilot-smoke.sh
bash scripts/butler-dev-live-flywheel-checklist.sh --probe   # 可选
```

网关 dev 委派（若走 terminal verify）需 `BUTLER_DEV_ENGINE=1`、`BUTLER_TERMINAL_PROFILE=dev`；Lead 生产网关可 terminal=0，委派仍可用。

---

## 3. 微信 Owner 飞轮（约 15 分钟）

按顺序发微信（当前项目 = **演示试点**）：

| 步 | 命令 / 话术 | 期望 |
|----|-------------|------|
| 1 | `/切换 演示试点` | 切换成功 + **项目摘要**（待办/委派） |
| 2 | `/状态` 或 `/简报` | 顶部 **健康灯** 🟢🟡🔴 |
| 2b | `/今日` | 本项目 **优先事项** 一屏 |
| 3 | `/诊断` | **简要诊断**（非技术）；运维用 `/诊断 详细` |
| 4 | 自然语言：`请委派开发代理：在 DemoPilot/README.md 末尾加一行「最后验收：YYYY-MM-DD」` | 异步则见「已接单 → 执行中 → 完成后通知」 |
| 5 | 等待委派完成推送 | 含 headline + **发 /详细** 提示 |
| 6 | `/详细` | 完整委派报告 |
| 7 | `/运行 test-unit-smoke` | runtime 只读 pytest 子集 PASS |
| 8 | `/简报` | 待办/待审汇总；无异常则 ✅ |

**记录**：在 `projects/DemoPilot/docs/pilot-log.md`（gitignore 可本地）写一行日期 + 成败。

---

## 4. CLI 等价（无微信时）

```bash
bash scripts/butler-pilot-dev-testing.sh
bash scripts/butler-demo-pilot-smoke.sh
bash scripts/butler-wechat-dev-delegate-sim.sh --track demopilot
PYTHONPATH=. pytest tests/gateway/test_project_commands.py -q
```

---

## 5. 与 CC/Cursor 的分工（Owner 话术）

- **重编码、大 refactor**：本机 Claude Code / Cursor  
- **远程派工、验收、记忆、多项目**：微信 Butler  
- 演示试点 **不** 验证 novel-factory；小说能力见 **灵文1号**

---

## 6. 相关

- [`pilot-setup.md`](pilot-setup.md) — 5 分钟冒烟  
- [`../README.md`](../README.md) — 项目说明  
- [`docs/guides/project-onboarding.md`](../../../docs/guides/project-onboarding.md) — 接入清单
