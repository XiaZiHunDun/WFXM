# Butler 月度 Dev 飞轮（真机话术）

> **主路径**：Butler `delegate_task` + dev 工具链（**不用** `/cc-bridge`）  
> **自动化**：`bash scripts/butler-dev-flywheel-monthly.sh`  
> **决策 SSOT**：[`butler-system-assessment-and-ops-2026-06.md`](../plans/decisions/butler-system-assessment-and-ops-2026-06.md)

---

## 1. 每月自动化（发微信前跑）

```bash
cd /path/to/WFXM
bash scripts/butler-dev-flywheel-monthly.sh
```

通过后再做下面 **一条** 微信真机验收（或自动化等价探针）。

```bash
# 自动化：Owner 会话 + §2A 话术（推荐，无需手打微信）
bash scripts/butler-wechat-manual-flywheel-probe.sh --push --log
```

手打微信见下文 §2。

---

## 2. 微信真机话术（选 A 或 B）

### A. 灵文1号 — 标准飞轮（推荐）

```
/切换 灵文1号

请 delegate_task，role=dev（禁止 content）：
在 docs/ 写 dev-flywheel-manual-YYYY-MM-DD.md，正文仅一行「月度验收 YYYY-MM-DD」；
先 read_file 确认不存在再 write_file，写后再 read_file 确认；不要改其它文件。
```

**期望**：委派成功 → `/详细` 可见文件 → 可选 `/测试` 或等 dev VERIFY。

### B. 演示试点 — 轻量只读

```
/切换 演示试点

请委派开发代理：read_file README.md 前 15 行并中文摘要，不要改文件。
```

**期望**：摘要含 DemoPilot / Butler；无 `File not found`。

---

## 3. 验收勾选

| # | 项 | ☑ |
|---|-----|---|
| 1 | 委派回复含「开发」/ task_id | |
| 2 | `/详细` 有变更或读文件证据 | |
| 3 | 无 `LingWen1/` 路径错误 | |
| 4 | `/诊断` 无异常僵死委派 | |

---

## 4. 记录

通过后在 `projects/LingWen1/docs/pilot-log.md` 追加一行，或：

```bash
bash scripts/butler-dev-flywheel-monthly.sh --log
```

---

## 5. 失败时

| 现象 | 动作 |
|------|------|
| terminal 沙箱失败 | `/沙箱` · `/批准沙箱外 pytest …` |
| 路径错误 | 查 Lead prompt §路径纪律 |
| 委派无工具 | `/诊断` · `butler-wechat-dev-delegate-sim.sh --track lingwen` |
