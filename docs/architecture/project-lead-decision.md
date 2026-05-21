# 项目 Lead 架构决策（ADR）

> **状态**：已采纳（2026-05-21）  
> **决策者**：主公确认  
> **关联**：[`v4-architecture.md`](v4-architecture.md)、[`memory-roadmap.md`](memory-roadmap.md)、灵文试点 [`projects/LingWen1/docs/project-lead-scope.md`](../../projects/LingWen1/docs/project-lead-scope.md)

---

## 1. 产品主句（对外）

**莎丽是你的终身管家；进入某个项目后，由该项目的厂长（Project Lead）在莎丽背后替你统筹，需要动手时再派开发 / 内容 / 审核代理。**

用户仍只面对 **一个微信 Bot、一套斜杠命令**；不在产品上制造「两个聊天对象」。

---

## 2. 架构原则（对内）

| 原则 | 说明 |
|------|------|
| **门户单一** | 网关、Owner 画像、跨项目经验、安全与委派深度 — 归平台管家层 |
| **项目主控下沉** | 长周期、强领域、流水线状态 — 归项目 Lead，不堆进通用管家提示词 |
| **工人无状态** | `dev` / `content` / `review` 仍通过 `delegate_task` 单次拉起，禁止再委派 |
| **运行时分级** | 脚本与 `workflow_state.json` 为真相源；Lead **读状态、派步、汇报**；全平台 7×24 调度 **非当前承诺** |
| **渐进演进** | 先配置与工具增强，再 Lead 专用 Loop，最后可选定时任务 |

---

## 3. 莎丽（管家）vs 项目 Lead 职责矩阵

| 职责 | 莎丽 Butler | 项目 Lead（如灵文厂长） | 工人 dev/content/review |
|------|-------------|-------------------------|-------------------------|
| 微信唯一对话入口 | ✅ | ❌（对用户不可见为第二 Bot） | ❌ |
| `/切换` `/项目` `/状态` | ✅ | ❌ | ❌ |
| Owner 画像、跨项目经验 | ✅ 读写 | ❌ | ❌ |
| `/记忆待审` `/批准记忆` `/诊断` | ✅ | ❌（可读项目 MEMORY 摘要） | ❌ |
| `/新对话` 清空**会话**聊天 | ✅ | 服从会话边界 | — |
| 项目 MEMORY、向量、试点事实 | 切换时加载；可 `butler_remember` | ✅ 主责解读与更新建议 | 仅本次任务上下文 |
| 读懂 `workflow_state` / 工厂阶段 | 概要 | ✅ 主责 | 按 Lead 给的单步任务 |
| 拆解多步流水线、决定下一步 | 可转交 Lead | ✅ | ❌ |
| `delegate_task` | ✅ 可直接派（过渡期） | ✅ 主路径 | ❌ 禁止 |
| `run_workflow` / `/工作流` | ✅ 可触发 | ✅ 主路径 | ❌ |
| 项目内 `write_file` / `run_shell` | ❌ 提示词禁止 | ❌（Lead 不亲自改盘） | ✅ |
| 简单只读（README 几行） | ✅ | 可代劳 | 通常不必 |
| 定时批量发布 / 无人值守改稿 | ❌ | ❌（首期） | ❌ |

**冲突时**：项目内「下一步干什么、工厂卡在哪」以 **Lead** 为准；「换项目、记偏好、记忆待审」以 **莎丽** 为准。

---

## 4. 明确不选 / 非承诺范围

| 未采纳为主方向 | 原因 |
|----------------|------|
| **纯①** 永远只有莎丽、无项目 Lead | 与灵文级复杂度错位；主控上下文无法沉淀 |
| **纯③** 平台 7×24 代每个项目跑完整流水线 | 实现与运维风险高；与「对话驱动」主路径不符 |
| Lead 作为第二个微信 Bot | 交互分裂、记忆与命令重复 |

**③ 的合法形态（远期、可选）**：仅对 **已验收、可回滚** 的脚本步骤（如一致性扫描）做「触发 + 通知」，且默认 **人工批准** 后才执行写操作。

---

## 5. 分阶段路线图

### 阶段 0 — 当前基线（已完成）

- 管家 + `delegate_task` + 项目 MEMORY / 向量 / M1–M4  
- 微信核心场景与灵文试点冒烟  
- `novel-factory` 以仓库脚本 + `workflow_state.json` 为主  

**验收**：[`wechat-core-scenario.md`](../guides/wechat-core-scenario.md)、[`wechat-daily-smoke-checklist.md`](../guides/wechat-daily-smoke-checklist.md)

---

### 阶段 1 — 秘书壳 + 灵文配置（近期，低风险）✅ 2026-05-21 真机通过

**目标**：不换 Loop 架构，把「厂长脑」装进配置与工具。

| 项 | 交付 |
|----|------|
| 灵文 Skill | `projects/LingWen1/skills/lingwen-project-lead.md` → `sync-lingwen-project-skills.sh` |
| 工具 | Lead 级只读：`workflow_state`、当前 phase/step 摘要（可复用 `read_file` + Skill） |
| 管家提示 | 在 `current_project=灵文1号` 时优先 `/工作流` 或委派，少直接改盘 |
| 工作流 | 扩展内置 DAG 或文档化「哪几步必须走脚本」 |

**验收（建议）**

- [x] 微信问「流水线当前 phase/step」能答对（读 state，不瞎编）  
- [x] 委派 content 写 `docs/`，管家不直接改盘  
- [x] `/工作流 list` 与 pilot 文档一致（阶段 1 范围）  

**风险**：低；主要是配置与文档漂移，需跟 `workflow_state.json` 同步。

---

### 阶段 2 — 项目 Lead Loop（中期）✅ 2026-05-21 真机通过

**目标**：`/切换 灵文1号` 后，**会话主推理面**绑定 Lead（独立 system prompt + 工具策略），莎丽仅负责未切换时的门户行为。

| 项 | 交付 |
|----|------|
| `role=lead` 或等价 | `agent_profiles.py` + `create_project_agent_loop(role=lead)` |
| 会话绑定 | `session_key` 含项目；Lead Loop 长历史（不受 `/新对话` 误清项目 MEMORY） |
| 工具集 | 读 state、列工作流、`delegate_task`、`run_workflow`；**无** write/shell |
| 切换 UX | 回复含「已进入灵文厂长模式」类一句（仍同一 Bot） |

**验收（建议）**

- [x] 同项目连续 3 轮以上，Lead 能引用上一轮工厂结论（无需用户重复 phase）  
- [x] Lead 不直接 `write_file`；写操作 100% 经 delegate  
- [x] `/新对话` 后 Lead 会话历史清空，但 MEMORY / state 只读仍正确  
- [x] `/诊断` 显示「对话引擎: 项目 Lead（厂长）」  

**风险**：中 — Lead 与管家边界、记忆 scope、模型是否听 Lead 指令；需 `/health` 与工具审计。（试点已验收）

**代码落点**：`butler/project_lead.py`、`butler/prompts/lingwen_lead_system.md`、`orchestrator.build_lead_system_prompt`、`gateway/message_handler._create_loop_for_session`、`project_tools` Lead 白名单；`BUTLER_LEAD_PROJECTS` 可扩展厂长项目列表。

---

### 阶段 3 — 运行时自动化（3a–3c 已实现，3d 已落地）

**目标**：局部 ③，不上升为全平台主句。完整方案见 **[`project-runtime-automation.md`](project-runtime-automation.md)**；运维见 **[`guides/runtime-ops.md`](../guides/runtime-ops.md)**。

| 子阶段 | 交付 | 状态 |
|--------|------|------|
| 3a | CLI `runtime run/list` + 只读 job + `/定时` `/运行` + 微信推送 | ✅ 微信验收 2026-05-21 |
| 3b | `jobs.yaml` + `runtime due` + systemd timer（15min） | ✅ 已安装；定时真机验收暂缓 |
| 3c | `approval` + `/批准运行`（mutating 默认关） | ✅ 已实现；改盘真机验收暂缓 |
| 3d | Lead Skill 建议 `/运行`；`/诊断` 显示最近 runtime | ✅ 2026-05-21 |

| 项 | 条件 |
|----|------|
| 定时一致性扫描 | 只读报告推微信；改盘须批准 |
| 发布 / 汇总 | 必须批准 + `enabled: true` |
| 失败告警 | audit + 微信（逻辑已有，可按需验） |

**验收**：见 [`project-runtime-automation.md`](project-runtime-automation.md) §10（部分项随 3b/3c 真机延后）。

---

## 6. 能力效果与风险（决策摘要）

| 维度 | 采纳方案（① 壳 + ② 魂） |
|------|-------------------------|
| 复杂项目（灵文） | 阶段 1–2 后可达「主控懂厂 + 工人执行」 |
| 多项目扩展 | 每项目一份 Lead profile + Skill，莎丽不变 |
| 用户学习成本 | 低（仍只认莎丽） |
| 实现风险 | 阶段 1 低、阶段 2 中、阶段 3 高且可选 |
| 与现有投入 | 委派 / TaskOrchestrator / MEMORY 全部复用 |

---

## 7. 备选方案记录

| 方案 | 未作为主方向的原因 |
|------|---------------------|
| 仅① 莎丽兼任所有项目厂长 | 灵文流水线状态与长周期上下文易超载；与主公初设「每项目主控」不符 |
| 仅③ 7×24 平台运转 | 离对话型网关太远；内容与发布类误操作不可逆 |
| 每项目独立微信 Bot | 运维与记忆割裂；不符合当前单租户试点 |

---

## 8. 文档与试点索引

| 文档 | 用途 |
|------|------|
| 本文 | 平台级 ADR |
| [`projects/LingWen1/docs/project-lead-scope.md`](../../projects/LingWen1/docs/project-lead-scope.md) | 灵文 Lead v1 五条能力、禁止项、话术 |
| [`wechat-core-scenario.md`](../guides/wechat-core-scenario.md) | 微信回归剧本 |
| [`memory-guide.md`](../../projects/LingWen1/docs/memory-guide.md) | 记忆与厂长职责交叉引用 |

---

## 9. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-05-21 | 初版：主公认可「① 壳 + ② 魂」分阶段决策 |
