# 灵文1号 · 维护态 / 新书态双剧本（B1）

> **理论**：T8 管家-委派分离 — Lead 只读统筹，改盘走委派或 runtime 批准链。  
> **状态源**：`project.yaml` → `lifecycle: complete`；`novel-factory/workflow_state.json` → `PHASE_COMPLETE` / `STEP_25`。

---

## 何时选哪条剧本

| 剧本 | 触发条件 | Lead 主路径 |
|------|----------|-------------|
| **维护态** | `lifecycle: complete` 且主公未声明新选题 | 读 state → `/运行` 只读 job → 委派 dev 只读检查 |
| **新书态** | 主公明确「新开一本 / 新选题 / 新卷」 | 指引 `run_workflow.sh` 早期步骤；**不**无人值守跑完全厂 25 步 |

当前默认：**维护态**（《星陨纪元》v3.0 已发布完结）。

---

## 维护态 — 微信验收一句

```
当前灵文1号是什么阶段？请读 workflow_state 后摘要，并建议今天适合跑哪个只读巡检。
```

**预期**：答 `PHASE_COMPLETE` / `STEP_25`；建议 `factory-status-daily` 或 `consistency-weekly`；**不**直接 `terminal` 改盘。

**深化（B2/B3）**：

| # | 发送 | 预期 |
|---|------|------|
| M1 | `/运行 factory-status-daily` | 收到 workflow 摘要或 audit 路径 |
| M2 | `请委派开发代理：只读检查 docs/wechat-smoke.md 是否存在，不要改任何文件` | 明确已委派；Lead 不亲自 patch |
| M3 | `/运行 publish-preflight` | 只读预检通过或附报告路径 |
| M4 | `/运行 publish-archive` | **被拒**（mutating 须 `/批准运行`） |

---

## 新书态 — 微信验收一句

```
我想新开一本小说，不是维护星陨纪元。请说明要从 workflow 哪一步开始，以及你会委派谁做什么。
```

**预期**：

- 说明需主公确认选题/卷纲，**不**假设从 STEP_1 自动开跑
- 指引 `novel-factory/tools/workflow/run_workflow.sh` 或早期 phase 文档
- 提议 `butler_remember` 记「新书立项」备忘（可能进 Pending）
- **禁止** Lead 直接 `write_file` 到 `08_已发布/` 或正文目录

**深化**：

| # | 发送 | 预期 |
|---|------|------|
| N1 | `记住：新书选题暂定为《测试书名》，先只做立项备忘` | 提示 `/记忆待审` 若 Pending |
| N2 | `请委派内容代理：在 docs/ 写 new-book-intent.md，只写选题一句话和日期，不要动 novel-factory 正文` | content 委派；文件落在 `docs/` |

---

## 自动化守门

```bash
bash scripts/butler-lingwen-lead-smoke.sh
bash scripts/butler-wechat-dual-playbook-probe.sh --quick   # B1 静态 + 有 key 时 handler 各测一句
bash scripts/butler-runtime-smoke.sh 灵文1号
bash scripts/butler-phase4-smoke.sh
bash scripts/butler-delegation-boundary-smoke.sh  # P1 #4 — content vs dev 路径边界（spec §2.3）
```

## 相关

- Skill：`projects/LingWen1/skills/lingwen-project-lead.md`
- Runtime 任务：`runtime/jobs.yaml`
- 真机主清单：[`docs/guides/wechat-daily-smoke-checklist.md`](../../../docs/guides/wechat-daily-smoke-checklist.md)
