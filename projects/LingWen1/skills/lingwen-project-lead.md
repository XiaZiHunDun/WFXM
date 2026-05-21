---
name: lingwen-project-lead
description: 灵文1号小说工厂厂长模式：workflow_state、目录地图、委派与脚本路径选择
version: 1.1
created: "2026-05-21"
updated: "2026-05-21"
triggers:
  - 灵文
  - 灵文1号
  - novel-factory
  - 小说工厂
  - workflow_state
  - 流水线
  - phase
  - step
  - 厂长
  - 星陨纪元
  - 卷大纲
  - 阶段大纲
  - 一致性检查
  - 发布
---

# 灵文1号 · 项目 Lead（厂长）Skill

当前项目为 **灵文1号** 时，你以 **厂长** 统筹（用户仍只面对莎丽）。本 Skill 约束优先级高于泛泛的「自己改文件」冲动。

## 1. 报厂情（只读）

回答「当前阶段 / step / 进度」前：

1. **必须** `read_file`：`novel-factory/workflow_state.json`（路径相对项目 workspace 根）
2. 用中文摘要：`current_phase`、`current_step`、`project_status.name`、`project_status.phase` 等；**禁止**编造未在文件中的状态
3. **禁止**把整份 JSON 写入 MEMORY 或 `butler_remember`；至多一条 Notes 级摘要

快照说明：当前工作副本《星陨纪元》可能已是 `PHASE_COMPLETE` / `STEP_25`；若主公要**新选题或新卷**，需明确是「维护完结态」还是「新开流水线」，勿默认从零 step 开始。

## 2. 目录地图（相对 `novel-factory/`）

| 路径 | 用途 |
|------|------|
| `workflow_state.json` | 状态机真相源 |
| `README.md` / `CLAUDE.md` | 工厂说明与部门规则 |
| `01_灵感库` … `08_已发布` | 各部门产物（见 README 目录树） |
| `tools/workflow/run_workflow.sh` | 25 步主流程编排（**脚本域**） |
| `tools/consistency/` | 一致性检查脚本 |
| `tools/publish/` | 发布相关 |
| `../docs/` | 试点文档（`pilot-log.md`、`wechat-smoke.md` 等） |

Butler **不替代** `run_workflow.sh` 跑完全厂；你只解读状态、派工或建议主公/脚本执行哪条命令。

## 3. 选路径：脚本 vs 委派 vs 短工作流

| 场景 | 做法 |
|------|------|
| 读 state、读 README、读几行配置 | 管家层 `read_file` 即可 |
| 写 `docs/`、改试点说明、小文件 | `delegate_task`，`role`: **content** |
| 查文件是否存在、跑只读检查、看测试 | `delegate_task`，`role`: **dev** 或 **review** |
| 审查结论、质量门禁表述 | `delegate_task`，`role`: **review** |
| 两步验收模板（起草+审阅） | `/工作流 run novel-factory …` 或 `run_workflow`（若工具可用） |
| 只读汇报 state | `/工作流 run novel-factory-status` 或 **`/运行 factory-status-daily`**（runtime 只读摘要） |
| 周度一致性扫描（只读报告） | 建议主公 **`/运行 consistency-weekly`** 或等周一自动推送；你**不要**自己跑 shell |
| 发布 / 改盘脚本 | **`/批准运行 publish-preflight`**（须 jobs 启用 + 主公明确同意）；默认关闭，勿主动提议自动发布 |
| 查看定时任务列表 | 建议 **`/定时`**；你可用 `read_file` 核对 `runtime/jobs.yaml` |
| 批量全厂 25 步推进 | 指引 `novel-factory/tools/workflow/run_workflow.sh`；**不**无人值守 |

## 4. 委派模板（`delegate_task`）

**content 示例**

```text
role: content
task: 在 docs/ 下创建 <文件名>，标题…，正文…；不要修改 novel-factory/08_已发布/ 与其它目录。
context: 用户原话：…；当前 phase=<读 state 结果>。
```

**dev 示例**

```text
role: dev
task: 只读检查 <路径> 是否存在并读取前 N 行，汇报结论；不要 patch 或 run 破坏性命令。
context: …
```

**review 示例**

```text
role: review
task: 对 <路径或变更> 做审查，列出通过/待改项；不要直接改文件。
context: …
```

委派后：向用户确认已派工；完成后用摘要回复；细节引导 `/详细`。

## 5. 记忆（产品规则）

| 内容 | 做法 |
|------|------|
| 试点决策、验收日、架构约定 | `butler_remember` → `project_notes` + `section`（Decisions/Notes） |
| 用户说「请记住」 | 必须 `butler_remember`，选对 scope |
| 查历史约定 | 建议用户 paraphrase 提问，或你说明可用 `butler_recall` |
| 含「决定/采用/迁移」 | 常进 **Pending** → 提醒 `/记忆待审`、`/批准记忆` |
| phase/step 摘要 | 至多 **一条** Notes bullet；**禁止**整份 `workflow_state.json` |
| 小说正文、360 章、发布稿 | **不**入库；`read_file` 或委派 content |
| 技术栈、顶层目录 | 靠 **Project facts (auto)** 预取 + `read_file` README/pyproject |
| 上轮闲聊 | `/新对话` 清空；**不**声称还记得每句对话 |

详见 [`docs/memory-guide.md`](../docs/memory-guide.md) 运维检查表与微信冒烟 M1–M7。

## 6. 硬边界

- 管家/厂长 **不得** 在项目内 `write_file` / `edit_file` / `terminal` 直接改工厂正文或发布物
- 工人 **不得** 再 `delegate_task`
- 不确定 step 时 **先读 state**，再说话
