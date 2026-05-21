# 灵文1号 · 项目 Lead（厂长）范围说明

> **平台决策**：[`docs/architecture/project-lead-decision.md`](../../../docs/architecture/project-lead-decision.md)  
> **试点状态**：阶段 1–2 **真机验收通过**（2026-05-21）  
> **项目**：`灵文1号` · `projects/LingWen1/`

---

## 1. 灵文厂长是谁

- **对用户**：仍只和 **莎丽** 说话；切换到灵文后，莎丽背后由 **灵文 Lead（厂长）** 承担项目主控逻辑。  
- **对系统**：拟议 `role=lead`（阶段 2）或当前阶段由 **莎丽 + 灵文 Skill** 代理厂长职责。  
- **不是**：第二个微信 Bot；不是替代 `novel-factory/` 里已有 shell 流水线引擎。

---

## 2. Lead v1 必须会的五件事

| # | 能力 | 做什么 | 真相源 / 工具 |
|---|------|--------|----------------|
| 1 | **报厂情** | 回答当前 **phase / step**、上一轮卡在哪 | `novel-factory/workflow_state.json`；只读 |
| 2 | **选路径** | 下一步是 **跑规定脚本** 还是 **委派工人**，说清理由 | Skill + `09_规范文档` / `.workflow_rules`；不猜 |
| 3 | **派工人** | 写正文 / 改代码 / 只读审查 → `delegate_task` 对应 `content` / `dev` / `review` | `task` + `context` 含路径与「不要改 X」 |
| 4 | **跑短 DAG** | 适合两步模板时用 `/工作流 run novel-factory` 或 `run_workflow` | 内置 YAML；不等同 25 步全厂 |
| 5 | **沉淀记忆** | 架构决策、试点进度 → `butler_remember` `project_notes` 或提醒主公 `/记忆待审` | MEMORY.md + 向量；不整份 JSON 入库 |

**阶段 1**：五件事由莎丽在加载灵文 Skill 后执行；**阶段 2**：五件事绑定 Lead Loop 的系统提示与工具白名单。

---

## 3. 禁止项（Lead / 代理厂长的硬边界）

| 禁止 | 原因 |
|------|------|
| Lead / 莎丽在项目内 **`write_file` / `edit_file` / `run_shell`** 直接改工厂正文或发布 | 与管家层规则一致；改盘只经工人 |
| 把 **`workflow_state.json` 整份**写入 MEMORY 或 `butler_remember` | 机读状态 ≠ 长期记忆；最多一条 Notes 摘要 |
| 工人 **`delegate_task` 再委派** | 深度与工具策略已限制 |
| 未读 state 就声称「全厂已完成」 | 必须以 state + 磁盘抽查为准 |
| 阶段 1–2 承诺 **无人值守批量发布 / 定时改稿** | 属平台阶段 3，灵文首期不做 |

---

## 4. 与 `novel-factory` 的关系

```text
你 → 莎丽（门户）→ 灵文 Lead（统筹）
                      ├→ delegate → content / dev / review（单次任务）
                      ├→ /工作流 → 2 步 Butler DAG（draft/review 等）
                      └→ 指引你或脚本 → novel-factory/tools/*.sh（25 步主流程）
```

| 层级 | 职责 |
|------|------|
| **Butler 2 步工作流** | 个人助手验收、短文案；已纳入 [`wechat-core-scenario.md`](../../../docs/guides/wechat-core-scenario.md) 步骤 8 |
| **novel-factory 脚本 + state** | 卷宗生产、一致性、发布；**厂长负责解读与派单，不替代脚本执行** |
| **项目 MEMORY** | 决策、约定、试点日期；与 [memory-guide.md](memory-guide.md) 一致 |

---

## 5. 微信话术示例（验收用）

| 意图 | 用户可说 | 预期行为 |
|------|----------|----------|
| 看厂 | `当前小说工厂 phase 和 step 是什么？` | 读 state，简短中文回答 |
| 派活 | `请交给内容代理：在 docs 写 …，不要改其他文件` | `delegate_task` content；摘要 + 可选 `/详细` |
| 检查 | `委派开发代理：只读检查 docs/xxx 是否存在` | `delegate_task` dev；不 patch |
| 短流 | `/工作流 run novel-factory …` | 两步 DAG 摘要 |
| 记忆 | `请记住：…` → `/记忆待审` | `butler_remember`；Pending 流程 |

**不应出现**：莎丽/Lead 自己说「我已写好文件」却未委派；未读 state 编造 phase。

---

## 6. 阶段 1 实施清单（灵文）

- [x] **灵文 Skill**（git 源 [`../skills/lingwen-project-lead.md`](../skills/lingwen-project-lead.md)，部署：`bash scripts/sync-lingwen-project-skills.sh`）  
- [x] **厂长模式钩子**：`butler/workflows/hooks.py` → 网关/CLI `pre_llm_call` 注入（`current_project=灵文1号`）  
- [x] [`pilot-log.md`](pilot-log.md) 记录阶段 1 实施  
- [x] **微信验收**（§5 话术表）：读 phase/step、委派写 docs、不直接改盘 — **2026-05-21 主公确认通过**

---

## 7. 阶段 2 验收清单（Lead Loop）

- [x] `/切换 灵文1号` 后回复含 **「厂长模式」** — **2026-05-21 主公确认通过**  
- [x] `/诊断` 显示 **「对话引擎: 项目 Lead（厂长）」**  
- [x] 连续多轮可引用上轮工厂/委派结论  
- [x] 工具审计：Lead 无 write/shell；委派有记录  
- [x] `/新对话` 清空聊天但读 state / MEMORY 仍正确  

---

## 8. 阶段 3（运行时自动化）

- 设计：[`docs/architecture/project-runtime-automation.md`](../../../docs/architecture/project-runtime-automation.md)  
- 运维：[`docs/guides/runtime-ops.md`](../../../docs/guides/runtime-ops.md)  
- 任务表：[`../runtime/jobs.yaml`](../runtime/jobs.yaml)  

**已实施**：微信 `/定时`、`/运行`（只读）、`/批准运行`（改盘）；CLI `butler runtime …`；timer 每 15 分钟 `due`。  
厂长对话中优先 **建议** 主公用 `/运行` / `/定时`，不自行跑 `novel-factory/tools` shell（见 Skill §3）。  
3b/3c **定时与改盘批准** 真机验收主公按需进行。  
**不实施**：`workflow-report` job、runtime 失败自动重试（state 汇报以日报 + 本 Skill 读 `workflow_state.json` 为准）。

## 9. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-05-21 | 初版：五条能力、禁止项、与 novel-factory 边界 |
| 2026-05-21 | 增加阶段 3 设计索引 |
| 2026-05-21 | 登记不实施 workflow-report、runtime 失败重试 |
