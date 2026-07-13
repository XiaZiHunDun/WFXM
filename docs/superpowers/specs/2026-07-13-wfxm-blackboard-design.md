# WFXM 黑板体系设计 — 多 Agent 班次交接

- **日期**：2026-07-13
- **作者**：Claude Code (brainstorming 会话)
- **状态**：Draft，待用户复审
- **作用域**：WFXM 仓库内（不跨仓、不进 `reference/`）

---

## 1. 背景与动机

WFXM 是个由 Butler v4 管理的多项目 Python 仓库。Owner 主公未来会让多种 AI 助手（Claude Code、Cursor、Codex 等）以及多个人类会话轮班开发 WFXM。今天已经存在的协调原语（`delegate_task` / `human_gate` / `project_todos` / `MEMORY.md` / `AGENTS.md` / 项目 backlog）虽各有职责，但有一个共性缺口：

> **跨 Agent、跨会话的状态没有结构化的"班次交接"层。**

具体来说，目前面对以下四个互相关联的问题：

1. **读写冲突 / 状态不一致**：异构 Agent 在不同时间读同一份状态文件，靠"git 兜底"但缺乏明确交接契约。
2. **上下文重复 / 断档**：每次会话从零读 AGENTS.md + 记忆，不知道上一班到底干了啥、未解决啥。
3. **委托 / 交接不顺畅**：不同 Agent 对"什么已完成、谁负责什么"口径不一。
4. **审计 / 复盘难**：散落在 git log + 聊天记录 + 项目 backlog，无统一追溯链。

这四个问题围着"共享状态"这一根轴。本 spec 设计一个**轻量、append-only、Markdown-based 的黑板层**，专门服务"班次交接"这一段，不替代现有原语。

---

## 2. 目标与非目标

### 目标

- 为异构 Agent 提供一个**无需新工具**就能读写的中央结构（Markdown + YAML frontmatter）。
- 让会话开始时**一眼看清**当前快照，无需翻 git log。
- 让会话结束时**append 一张班次卡**，完成硬性交接。
- 让仲裁人（主公）能**事后追溯**"谁、什么时候、做了什么、未做什么"。
- 解决上述 4 个痛点（冲突 / 上下文 / 交接 / 审计）。

### 非目标（YAGNI）

- **不**做实时推送、订阅、锁。
- **不**替代 `MEMORY.md` / `AGENTS.md` / `project_todos` / `human_gate`——只补班次交接这一段。
- **不**强制 Agent 写卡必须通过 Butler CLI——任何能 append Markdown 的工具都能参与。
- **不**做实时双向同步（避免 `tasks/backlog.yaml` ↔ `~/.butler/todos.json` 复杂度）。
- **不**做聚合报表（"本月 claude-code 完成多少 P1"）——超出当前 YAGNI。
- **不**进 `reference/`（那是主公维护的外部对照）。

---

## 3. 架构

```
                 ┌─────────────────────────────────────┐
                 │  WFXM/.blackboard/  （仓库内、git） │
                 │  ──────────────────────────────── │
                 │  README.md    规约契约             │
                 │  state.md     当前快照（手编）     │
                 │  shifts/      append-only 班次卡 │
                 │  tasks/       backlog + claims    │
                 │  log.md       班次摘要流           │
                 └─────────────────────────────────────┘
                                  ▲ 读
                                  │ 写
                ┌─────────────────┼─────────────────┐
                │                 │                 │
         Claude Code           Cursor            Codex
         (session start:       (手动触发/        (CLI/IDE 集成)
          读 state + 最新        Agent mode
          shift card, end:       读规约后写卡)
          append shift card)
                                  │
                                  ▼
                         人工仲裁：班次卡 review
                         后决定下次交接给谁
```

### 3.1 并发模型

**串行 + 人工仲裁**：同一时刻最多一个 Agent 写，靠"班次切换"隐式串行。仲裁人 review 上一班次卡，决定下次交接给谁。

### 3.2 目录布局

```
WFXM/.blackboard/
├── README.md                    # 规约：所有 Agent 必读；schema、契约、示例
├── state.md                     # 当前快照：active tasks / 阻塞 / 上一班次链接
├── log.md                       # 班次摘要流（每次新班次结束 append 一段）
├── shifts/
│   ├── 2026-07-13-claude-001.md
│   ├── 2026-07-13-cursor-002.md
│   └── ...
└── tasks/
    ├── backlog.yaml             # 跨 Agent 待办（可镜像 ~/.butler/todos.json）
    └── claims/                  # 谁认领了什么（防双抢）
        ├── 2026-07-13-claude-P2-#8.yaml
        └── ...
```

### 3.3 组件职责

| 组件 | 谁写 | 谁读 | 性质 |
|------|------|------|------|
| `README.md` | 人（首次建板时） | 所有 Agent | 静态契约 |
| `state.md` | 人工 + 班次结束聚合 | 所有 Agent（会话开始必读） | 可改快照 |
| `shifts/<file>.md` | 当值 Agent | 下一班 Agent | append-only |
| `log.md` | 当值 Agent 班次结束 | 人 / Agent | append-only 摘要 |
| `tasks/backlog.yaml` | Butler 或人工 | 所有 Agent | 可改 YAML |
| `tasks/claims/<id>.yaml` | 认领 Agent | 仲裁人 / 下一班 | 可改 YAML |

---

## 4. Schema

### 4.1 Shift card

存放路径：`shifts/<YYYY-MM-DD>-<agent>-<NNN>.md`，文件名即 `shift_id`。

```yaml
---
shift_id: 2026-07-13-claude-001     # 必填，YYYY-MM-DD-<agent>-<NNN>
agent: claude-code                   # 必填：claude-code | cursor | codex | opencode | human
session_window:                      # 必填；进行中时 end 可为 null
  start: 2026-07-13T09:00:00+08:00
  end: 2026-07-13T11:30:00+08:00
intent: "P2 #8 gateway test drift 修复收口"   # 必填，一行
scope:                               # 必填：本次触碰的路径列表
  - tests/gateway/
  - butler/gateway/
read_at_start:                       # 必填：会话开始读过的黑板文件
  - .blackboard/README.md
  - .blackboard/state.md
  - .blackboard/shifts/2026-07-12-codex-005.md
produced:                            # 可选：本次产出
  - type: commit
    ref: 323862e
    summary: "fix(tests): repair sprint migration drift failures"
  - type: doc
    ref: docs/plans/sprint-migration-drift-fix-2026-07-13.md
unresolved:                          # 可选：未解决项
  - "tests/gateway 63 pre-existing fail 待新 scope"
next_shift_recommendation:           # 可选：建议下一班给谁
  agent: cursor
  reason: "需要 IDE 内可视化 diff 走读"
  blocked_by: []
claim_ref: tasks/claims/P2-#8.yaml    # 可选：本次开了/关了哪个 claim
schema_version: 1                    # 必填：当前 = 1
---

## 详细叙述
（自由 Markdown：叙述、上下文、未尽事项）
```

### 4.2 state.md

```markdown
# WFXM BlackBoard State

_last_synced: 2026-07-13 11:35_
_last_shift: 2026-07-13-claude-001_

## 进行中
- [P2-#8] (claude-code) tests/gateway drift 修复收口；last 2026-07-13-claude-001

## 待仲裁 / 阻塞
- [P1-#4] content vs dev 委派边界待硬化为 smoke test；约定见 dual-playbook.md

## 待认领
- 详见 tasks/backlog.yaml

## 最近 5 个班次
- 2026-07-13-claude-001: P2 #8 drift 收口（323862e）
- 2026-07-12-codex-005: P2 #8 修复 9 个 drift fail
- ...
```

`_last_synced` / `_last_shift` 由人工或班次结束聚合时维护；Agent 读到时若 `_last_synced` 远早于当前班次，应再读最新 shift 卡。

### 4.3 tasks/backlog.yaml

```yaml
schema_version: 1
last_updated: 2026-07-13T11:35:00+08:00
tasks:
  - id: P2-#8
    title: "旧 sprint 测试迁入域目录"
    priority: P2
    status: done                      # open | claimed | in_progress | blocked | done | deferred
    claimed_by: claude-code
    claim_ref: tasks/claims/P2-#8.yaml
    refs:
      - file: projects/LingWen1/docs/interview-demo-backlog.md
        anchor: "P2 #8"
  - id: P1-#4
    title: "content vs dev 委派边界硬化"
    priority: P1
    status: open
    claimed_by: null
    refs:
      - file: projects/LingWen1/docs/interview-demo-backlog.md
        anchor: "P1 #4"
```

### 4.4 tasks/claims/<task-id>.yaml

```yaml
schema_version: 1
task_id: P2-#8
claimed_by: claude-code
claimed_at: 2026-07-13T09:05:00+08:00
expected_close_at: null
status: done                          # claimed | in_progress | done | abandoned | handed_off
handoff_to: null
shift_refs:
  - 2026-07-12-codex-005
  - 2026-07-13-claude-001
notes: "323862e 已落"
```

---

## 5. 生命周期

### 5.1 会话开始

1. 读 `.blackboard/README.md`（规约契约）
2. 读 `.blackboard/state.md`（当前快照）
3. 读 `shifts/` 最新 1-2 张班次卡（上一班上下文）
4. 若认领任务：改 `tasks/claims/<id>.yaml`（status `claimed` → `in_progress`）

### 5.2 会话中

可选：往 `log.md` append 重大事件（"完成 X，开始 Y"）。work 正常推进。

### 5.3 会话结束（hard gate）

1. 写 `shifts/<file>.md`（YAML frontmatter + 详细叙述）
2. append `log.md` 一段摘要（1-3 行）
3. 若开了 claim：更新 `tasks/claims/<id>.yaml`（含 `shift_refs`）
4. 若动了 backlog：更新 `tasks/backlog.yaml`
5. 可选：更新 `state.md`（让下个会话一眼看清）
6. commit 这一组黑板变更

---

## 6. 错误处理

| 失败模式 | 缓解 |
|---------|------|
| Agent 忘记写 shift 卡 | Butler session-end hook 检测今日是否缺卡并 warn（不阻断）；README 写明"shift 卡是 hard gate" |
| Shift card schema 不合规 | `butler blackboard validate` 在 commit 前自动跑；pre-commit hook 可选接入（轻量） |
| YAML 损坏（`backlog.yaml` / `claims/*.yaml`） | `safe_load` + 损坏 fallback 报警"黑板损坏，请人工修"；`state.md` 是 Markdown fallback |
| `shift_id` 冲突 | 文件名 = 日期+agent+当日序号，README 写"先看 shifts/ 今天最大序号 +1"；串行交接下几乎不撞 |
| Agent 读到过期 state.md | state.md 顶部 `_last_synced`；README 强调"读完 state.md 后必须再读最新 shift 卡" |
| 班次中途断电 | shift card 可分两步：start 时建 stub（`session_window.end` = null），end 时补全；或由下一班 Agent 补卡回填 |

---

## 7. 审计

- `git log .blackboard/` 即审计
- shift card 的 `produced[]` 链向 commits/docs
- `tasks/claims/<id>.yaml` 的 `shift_refs[]` 形成班次↔任务追溯链
- `butler blackboard audit --task <id>` 一键查询
- 不做聚合报表（YAGNI）

---

## 8. 测试

| 层级 | 内容 |
|------|------|
| Unit | YAML schema validator、`shift_id` 唯一性、`state_builder` 纯函数（若有）、`audit` 查询逻辑 |
| Integration（CLI） | `init / validate / snapshot / audit / handoff` 5 命令 |
| E2E smoke | 模拟一次完整班次：写卡 → validate → audit → 下一班读 → 接续 |
| 覆盖目标 | ≥ 80%（与项目规约一致） |

---

## 9. 集成点

| 现有原语 | 黑板如何衔接 |
|---------|--------------|
| `MEMORY.md` (auto-memory) | 不写进 MEMORY；黑板记 WFXM 项目内班次，MEMORY 仍记跨项目偏好/纪律 |
| `AGENTS.md` | §1 守门前加一行：`读 .blackboard/state.md` |
| `~/.butler/todos.json` | `butler blackboard sync-todos` 按需手动跑；**不做**实时双向同步 |
| `projects/LingWen1/docs/interview-demo-backlog.md` | `backlog.yaml.refs[]` 链向此文件；状态镜像或派生 |
| `butler/human_gate.py` | 不变；黑板只是事实源 |
| Sprint 进度 memory | 由 Agent 班次结束按需写；黑板不直接生成 |

---

## 10. 实施分阶段

| Phase | 范围 | 验收 |
|-------|------|------|
| P1 规约 + 模板 | `README.md`、`state.md` 模板、`backlog.yaml` 种子 | 3 文件可读；smoke 验 schema |
| P2 班次卡手工流程 | 写第一张 shift card + 一次性 schema 检查脚本（或 README 手动核对清单） | 一次完整班次跑通 |
| P3 CLI 工具 | `init / validate / snapshot / audit / handoff`（含把 P2 一次性脚本升级为正式 CLI） | 单测+集成测试 ≥ 80% |
| P4 集成 + hook | AGENTS.md 加指引、session-end 检测提醒、`sync-todos` | 跨原语走通 |
| P5 多 Agent 演练 | Cursor / Codex 各跑一次完整班次 | 异构 Agent 写卡格式一致 |

---

## 11. 风险与开放问题

| 项 | 说明 | 缓解 |
|----|------|------|
| Agent 漏写卡 | Butler 不强制；靠 hook + 人工兜底 | session-end 检测提醒；README 规约 |
| Cursor / Codex 不读规约 | IDE 类 Agent 启动流程不一定读 `.blackboard/README.md` | P5 演练时若发现，扩规约或加 IDE 插件 |
| YAML 与 Markdown 双轨脱节 | `backlog.yaml` 改了但 `state.md` 没更新 | `_last_synced` 字段 + validate 提示 |
| 多项目共用黑板 | 当前 spec 仅服务 WFXM 一仓 | 若以后要扩，spec 加 §12 "跨仓黑板" |

---

## 12. 关联文件

- Butler 入口：`AGENTS.md` / `STRUCTURE.md` / `butler/README.md`
- 现有协调原语：`butler/tools/project_todos.py` / `butler/human_gate.py`
- 项目 backlog：`projects/LingWen1/docs/interview-demo-backlog.md`
- Handoff 纪律：`~/.claude/projects/-home-ailearn-projects-WFXM/memory/feedback-handoff-discipline.md`

---

## 13. 决策记录（草稿）

- **2026-07-13**：选 A 方案（shift card 黑板）+ 仓库内位置 + 构建于现有原语之上 + 串行+人工仲裁。
- 决策者：主公（与 Claude Code brainstorming 会话确认）。