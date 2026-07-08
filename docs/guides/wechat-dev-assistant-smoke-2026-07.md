# 开发助手真机 / Handler 冒烟（十项）

> **更新**：2026-07-08 | 主场景：微信委派 **dev** 做读/写/测/审/删  
> **自动化**：`bash scripts/butler-wechat-dev-assistant-sim.sh`  
> **试点**：灵文1号（`projects/LingWen1/`）

---

## 1. 覆盖缺口（检查结论）

| 来源 | 开发向用例数 | 缺口 |
|------|-------------|------|
| `wechat-daily-smoke-checklist` 真机 | **1**（步骤 5 只读检查） | 无写码、pytest、patch、失败恢复 |
| `wechat-dev-delegate-scenarios` | **8**（含 content/review） | 偏验收剧本，非「日常开发助手」口语 |
| `wechat-owner-scenarios` delegate | **2** | 仅 content 写 + dev 只读 |
| **本指南 DEV-01–10** | **10** | 补齐开发主路径 |

**结论**：作为**开发助手**，原真机清单**不足**；须以本十项 + `butler-wechat-dev-assistant-sim.sh` 作发版前预演，真机按 §3 勾选。

---

## 2. Handler 模拟（推荐先发）

```bash
cd ~/projects/WFXM
bash scripts/butler-wechat-dev-assistant-sim.sh --quick   # 5 项，约 5–10 分钟
bash scripts/butler-wechat-dev-assistant-sim.sh           # 全 10 项，约 25–45 分钟
```

**2026-07-08 全量结果**：**8/10 PASS**（DEV-03/10 已修话术 + 产品门控后重跑；报告见 `.butler/reports/`）

**2026-07-08 修复**：
- DEV-03：话术改为 `read_file` + `write_file`（禁 patch/terminal）；复测磁盘 docstring 已落盘
- DEV-10：`wechat_minimal` 下 dev 子代理恢复 `delete_file`；委派 finalize 增加 `DELETE_VERIFY_GATE` 验盘

产物：`docs/dev-assistant-sim-YYYY-MM-DD.{py,md}`（sim cleanup 尽力删除）。

---

## 3. 真机话术（复制到微信）

默认项目：**灵文1号**。每项完成后在「通过」列打 ☑。

| ID | 发送内容（可复制） | 预期 | 通过 |
|----|-------------------|------|------|
| DEV-01 | 请委派开发代理：read_file 读 project.yaml，摘要 name 和 type，不要改文件 | 委派摘要；含灵文/software 等 | ☐ |
| DEV-02 | 请开发代理在 docs 建 `dev-assistant-manual-今天日期.py`，含 `def hello_dev(): return "ok"` | 委派完成；文件存在 | ☐ |
| DEV-03 | 给刚才的 py 加模块 docstring「Dev assistant manual」：先 read_file，再 write_file（禁 patch/terminal） | 修改成功；read 可见 | ☑ |
| DEV-04 | 对刚才 py 跑 `python -m py_compile`，报结果 | 无 SyntaxError | ☐ |
| DEV-05 | 请审核代理审查该 py，首行 PASS 或 FAIL | 审查结论 | ☐ |
| DEV-06 | 开发代理 list docs 目录并摘要 | 文件列表合理 | ☐ |
| DEV-07 | 开发代理 read `novel-factory/workflow_state.json`，说 phase/step | 与磁盘一致 | ☐ |
| DEV-08 | 写 `docs/dev-assistant-manual-今天.md` 一行验收戳，再 read 确认 | 写入+复读 | ☐ |
| DEV-09 | 删 `docs/不存在-dev-assistant.txt`，应说明失败/不存在 | 不编造成功 | ☐ |
| DEV-10 | 开发代理用 delete_file 删今天建的 dev-assistant-manual py/md（禁 terminal） | 文件已删；无假阳性 success | ☐ |

**运维**：`/开发状态` 宜显示 terminal=开、git_write=关（生产）；`/任务` 可查 task_id。

---

## 4. 与矩阵 / 试点门禁关系

| 链接 | 说明 |
|------|------|
| [`wechat-real-device-matrix-2026-07.md`](./wechat-real-device-matrix-2026-07.md) | 可增 DEV-01–10 行 |
| [`pilot-project-dev-testing.md`](./pilot-project-dev-testing.md) | 周门禁可追加本 sim |
| [`agent-testing-strategy-2026-06.md`](../plans/decisions/agent-testing-strategy-2026-06.md) | dev sim 属 opt-in live 层 |

---

## 5. 失败排查

| 现象 | 先看 |
|------|------|
| 不委派、自己 read | 话术含「开发代理」「role=dev」；`/分工` |
| File not found | 路径勿加 `LingWen1/` 前缀 |
| py_compile 被拒 | `.env` `BUTLER_ENABLE_TERMINAL=1`；`/开发状态` |
| 真机与 sim 不一致 | 先跑 sim 绿再真机；记入 pilot-log |
| 删除假阳性 | 看 task 是否 `DELETE_VERIFY_GATE`；确认 dev 有 `delete_file` |
