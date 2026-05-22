# 项目层微信化规划（单项目打磨 → 多项目）

> **状态**：规划稿（2026-05-22）  
> **目标**：在微信上完成项目的**开发、测试、运行**；当前以 **灵文1号** 打磨单项目闭环，成熟后再扩展多项目。  
> **关联**：[`project-lead-decision.md`](project-lead-decision.md)、[`dev-ops-tools-design.md`](dev-ops-tools-design.md)、[`project-runtime-automation.md`](project-runtime-automation.md)

---

## 1. 产品目标与边界

### 1.1 目标陈述

| 层级 | 用户看到什么 | 系统做什么 |
|------|--------------|------------|
| **平台** | 一个微信 Bot（莎丽） | 鉴权、记忆、切换、斜杠命令、安全沙箱 |
| **项目** | `/切换 灵文1号` 后进入「厂长模式」 | Lead 统筹：读状态、派工、触发短工作流 / runtime 只读任务 |
| **执行** | 「交给开发代理改…」「运行一致性检查」 | 工人改代码；runtime 跑脚本；**不是** Lead 亲自改盘 |

### 1.2 当前基线（代码事实）

- 项目 SSOT：`projects/<目录>/project.yaml`，由 `ProjectManager` 扫描 `BUTLER_PROJECTS_DIR`。
- 新建：`butler create <名> --type software` → 空目录 + 默认 tools 列表（**仅 CLI**，微信尚无「新建项目」）。
- 灵文1号：属 **迁入型** 项目（目录 `LingWen1`，显示名 `灵文1号`），含 `novel-factory/`、`runtime/jobs.yaml`、Lead Skill。
- 对话引擎：`BUTLER_LEAD_PROJECTS` / 默认 `灵文1号` → `gateway_loop_role=lead`（`butler/project_lead.py`）。
- 三条执行通道并存（见 §4）。

### 1.3 分期策略

```text
P0  单项目（灵文1号）  → 完结态/新书态话术 + 开发测试运行闭环验收
P1  项目接入规范      → 来源分类、导入/体检、project.yaml 模板
P2  能力包与边界硬化  → archetype、工具/通道矩阵、微信命令
P3  多项目            → 已有 chat 级绑定 + DemoPilot；补全发现/隔离/默认项
```

---

## 2. 项目分类：主类「有源码 / 无源码」（推荐）

可以**简化**：对用户和微信命令只暴露两档；实现上再用**二级标签**区分差异（不增加主类复杂度）。

### 2.1 主类（决定能力边界）

| 主类 | `project.yaml` 字段（拟） | 典型内容 | Butler 默认能力 |
|------|---------------------------|----------|-----------------|
| **有源码** `source: code` | 仓库、脚本、可跑测试 | 软件仓库、灵文+novel-factory、Git 导入目录 | 开发工具集 + 可选 Lead + runtime jobs；委派 **dev** 改代码 |
| **无源码** `source: none` | 文档/记忆/工作流为主 | 纯策划案、会议纪要项目、临时备忘仓 | **无** patch/terminal/git；委派 **content/review**；短工作流 |

**判定规则（体检时自动建议，可人工改）**：

- 目录下存在「可开发树」之一 → **有源码**：`.git`、`pyproject.toml`/`package.json`/`go.mod`、`src/`、`novel-factory/tools/` 等。
- 仅有 `docs/`、`.butler/`、`MEMORY.md`、办公文档 → **无源码**。

> 灵文1号：**有源码**（含 `novel-factory/` 大量脚本与正文树）。  
> 演示试点：若只有空 `docs/` 可标 **无源码**；若以后加代码再改为有源码。

### 2.2 二级标签（不增加主类，解决「来源不同」）

主类相同、**运营方式**仍可能不同，用 `tags` 或 `pack` 表达即可：

| 标签 | 含义 | 例子 |
|------|------|------|
| `origin:native` | Butler/CLI 新建的空或模板目录 | `butler create` |
| `origin:import` | Git/拷贝迁入，已有树 | 灵文1号、GitHub clone |
| `origin:attached` | 外挂 IDE 正在编辑同一目录 | Claude Code 已打开仓库 |
| `pack:novel-factory` | 带小说工厂脚本与 state | 灵文1号 |
| `lifecycle:complete` | 流水线已完结，偏巡检 | 灵文现况 |
| `lifecycle:active` | 仍在开发/创作 | 新书、软件迭代 |

微信主公只需理解：**有没有代码要写/要跑**；标签给 Lead Skill 和 preflight 用。

### 2.3 四种来源如何落入两档（对照表）

| 你原先关心的场景 | 主类 | 常见标签 |
|------------------|------|----------|
| 微信/CLI 新建空项目 | 有源码（空仓库也算，后续会加代码） | `origin:native` |
| GitHub 下载的项目 | **有源码** | `origin:import` |
| 环境上已有完整项目（灵文） | **有源码** | `origin:import` + `pack:novel-factory` + `lifecycle:complete` |
| Claude Code 正在跑的项目 | **有源码** | `origin:attached`（Butler 不控 CC，只绑定路径） |
| 只有文档/清单、无仓库 | **无源码** | `origin:native` |

**不再单独设第四类「外挂」**：外挂只是 **有源码 + attached**，避免分类爆炸。

### 2.4 接入时仍用统一流水线

```text
登记目录 → preflight（判有/无源码 + 建议 tags）
  → 写入 project.yaml（source + tags + tools 模板）
  → reindex → /切换
```

**有源码**模板：默认 tools 含 read/write/patch/terminal/git_*；可选 `lead`、`runtime/jobs.yaml`。  
**无源码**模板：仅 read/list/search + delegate + workflow + memory；**无** terminal/git。

---

## 3. 项目如何接入系统（统一注册模型）

### 3.1 最小接入契约（必须具备）

|  artifact | 作用 |
|-----------|------|
| `project.yaml` | 名称、type、tools、workflows、models、tenant |
| 可解析的 `workspace` 目录 | 工具 path_safety 的根 |
| 目录在 `BUTLER_PROJECTS_DIR` 下 | `ProjectManager` 能扫描到 |

### 3.2 推荐接入契约（具备更好微信体验）

| artifact | 作用 |
|-----------|------|
| `.butler/memory/MEMORY.md` | 项目记忆 SSOT |
| `skills/<project>-*.md` 或租户 skills | Lead/管家领域提示 |
| `runtime/jobs.yaml` | 测试/巡检/构建的**可重复**入口（微信 `/运行`） |
| `docs/pilot-setup.md` | 给人和 Agent 的「运营态说明」 |

### 3.3 注册流水线（建议固化为命令）

| 步骤 | CLI（已有/拟增） | 微信（拟增） |
|------|------------------|--------------|
| 发现 | `butler projects` | `/项目` 列表 |
| 体检 | `butler project preflight`（拟增） | `/项目 体检` |
| 注册 | 手写或 `butler project register` | `/项目 绑定 <路径>`（仅 Owner） |
| 激活 | `butler create` / 复制模板 | `/项目 新建` |
| 切换 | — | `/切换 <名>`（已有） |
| 向量 | `memory-reindex --project` | 运维脚本 / Lead 建议 |

### 3.4 `project.yaml` 拟增字段（P1/P2）

```yaml
# 示例：扩展字段（规划，非全部已实现）
name: 灵文1号
source: code                       # code | none — 主类（有源码 / 无源码）
tags: [import, novel-factory, lifecycle:complete]
lead: true                         # 有源码且需统筹时；或沿用 BUTLER_LEAD_PROJECTS
type: content                      # 保留兼容旧字段；可与 tags 并存
workspace: projects/LingWen1
runtime:
  jobs_file: runtime/jobs.yaml
tools: [...]                       # 由 source + tags 选模板，可再裁剪
workflows: [...]
```

**说明**：`workspace` 字段目前多用于展示；实际 workspace 以 `project.yaml` 所在目录为准（`Project.from_yaml`）。

---

## 4. 能力边界与划分（必须做）

### 4.1 三环 + 一条旁路

```mermaid
flowchart LR
  subgraph R0 [环0 平台 Butler]
    B[切换/记忆/诊断/斜杠]
  end
  subgraph R1 [环1 项目 Lead]
    L[读 state / 派工 / 工作流 / 建议 runtime]
  end
  subgraph R2 [环2 工人]
    W[write patch terminal git]
  end
  subgraph R3 [环3 Runtime 旁路]
    RT[argv 脚本 subprocess]
  end
  B --> L
  L -->|delegate_task| W
  L -->|run_runtime_job 只读| RT
  L -.->|禁止直接| W
  RT -->|mutating| APR[/批准运行/]
```

| 环 | 谁 | 工具/通道 | 硬规则 |
|----|-----|-----------|--------|
| **0 平台** | 莎丽（非 Lead 项目） | 全平台工具 + 跨项目记忆 | 不持项目写权限 |
| **1 Lead** | 厂长 | 只读文件 + `delegate_task` + `run_workflow` + `run_runtime_job`（只读 job） | **禁止** write/patch/terminal（`project_tools.py` 已强制） |
| **2 工人** | dev/content/review | `project.yaml` tools 白名单 | **禁止**再 `delegate_task`；路径限 workspace |
| **3 Runtime** | 系统定时/微信 `/运行` | `jobs.yaml` → shell | mutating 须批准 + `enabled`；与 Agent 工具审计分离 |

**微信网关生产默认值**（已实践）：`terminal=0`、`git_write=0`；开发走 **委派到 dev**，不在 Lead 线程开 shell。

### 4.2 能力模板 — 由「有/无源码」派生，tags 微调

| 模板 | 条件 | 默认 tools | workflows / runtime | Lead |
|------|------|------------|---------------------|------|
| `code-default` | `source: code` | read/write/patch/terminal/git_* | 按 tags 附加 | 若 `lead: true` |
| `code+novel-factory` | `source: code` + `pack:novel-factory` | 同上 | `novel-factory-status` + jobs.yaml | **是** |
| `none-default` | `source: none` | read/list/search + memory | 短工作流可选 | 通常否 |

灵文1号：`source: code`，`tags: [import, novel-factory, lifecycle:complete]` → 套用 `code+novel-factory`。

### 4.3 项目级限制（建议保持/强化）

| 限制项 | 机制 | 说明 |
|--------|------|------|
| 文件系统 | `path_safety` + `BUTLER_TOOL_SAFE_ROOT` | 项目 workspace 须在安全根下 |
| 工具列表 | `project.yaml` → `allowed_tool_names_for_project` | Lead 再子集裁剪 |
| 网络 git | 无 `git push/pull` 工具 | 降低远程破坏面 |
| Shell | argv 白名单 + 默认关闭 | 微信生产关 `BUTLER_ENABLE_TERMINAL` |
| 长脚本 | Runtime `timeout_seconds` + 批准门 | 与对话超时分离 |
| 记忆 | 分层：Owner / Experience / Project | 决策 Pending；禁止 state JSON 入库 |

### 4.4 「开发 / 测试 / 运行」在微信上的映射

| 用户意图 | 推荐通道 | 示例 |
|----------|----------|------|
| **开发**（改代码/docs） | Lead → `delegate_task` → dev/content | 「委派开发代理：只读检查…」「写 docs/…」 |
| **测试**（pytest/脚本） | ① dev 跑 `terminal`（网关开启时）② runtime job `test` ③ 本地 CI | 规划 job：`test-unit` readonly |
| **运行**（巡检/发布/一致性） | runtime readonly job；改盘 `/批准运行` | `/运行 factory-status-daily`、`consistency-weekly` |

避免让 Lead **亲手** `terminal` 跑测试；统一为「派 dev」或「登记 runtime job」。

---

## 5. 灵文1号：单项目打磨清单（P0）

在扩多项目前，建议把 **灵文1号** 做成「项目层样板」。

### 5.1 运营态双剧本（解决 state=COMPLETE 错位）

| 剧本 | 主公意图 | Lead 主路径 |
|------|----------|-------------|
| **维护态**（当前） | 看厂/巡检/预检 | 读 state → `/运行` / `run_runtime_job` → 摘要报告 |
| **新书态**（未来） | 新开一本小说 | 指引 `run_workflow.sh init` + 明确 **不** 自动 25 步；记忆记「新项目立项」 |

落点：`lingwen-project-lead` Skill + `pilot-setup.md` 各一节。

### 5.2 微信验收补项（项目层）

| 项 | 目的 |
|----|------|
| M5 facts 预取 | 项目层「懂仓库结构」 |
| Lead `run_runtime_job` → `publish-preflight` | 「测试/运行」不只 factory-status |
| 委派 dev：pytest 或 `npm test`（只读/短命令） | 「测试」闭环 |
| 可选 mutating 沙箱 | `/批准运行` 走一遍即关 |

### 5.3 工程项（可选）

- `scripts/butler-lingwen-lead-smoke.sh`：Lead 工具集 + workflow-state 只读断言。
- `project.yaml` 增加规划字段 `lifecycle: complete`（文档化即可，解析可后做）。

---

## 6. 多项目（P3 预览，本期不展开）

**已有**：`get_project_name_for_chat`、DemoPilot、`runtime due --all-projects`、每项目独立 session。

**待打磨**：

| 项 | 说明 |
|----|------|
| 默认项目 | `BUTLER_DEFAULT_PROJECT` vs 每 chat 绑定 |
| Lead 项目列表 | 扩展 `BUTLER_LEAD_PROJECTS`，不必硬编码仅灵文 |
| 隔离审计 | `/诊断` 标明当前项目；防止串记忆（已按项目隔离 MEMORY） |
| 能力包选择 | 新建/导入时选 archetype，而非复制灵文整包 |

---

## 7. 建议实施顺序

| 顺序 | 交付 | 预估 |
|------|------|------|
| 1 | 灵文 Skill 维护态/新书态 + M5–M7 微信验收 | 小 |
| 2 | 文档：`project.yaml` 扩展字段草案 + 接入检查表 | 小 |
| 3 | `butler project preflight`（目录检测、缺 project.yaml 提示） | 中 |
| 4 | 能力包模板目录 `docs/templates/project-archetypes/` | 中 |
| 5 | 微信 `/项目 新建` `/项目 体检`（Owner only） | 中 |
| 6 | Git 导入登记流程 + 示例 repo 试点 | 大 |
| 7 | 多项目 Lead 配置化 + 第二项目端到端 | 大 |

---

## 8. 决策记录（待主公确认）

| # | 问题 | 建议 |
|---|------|------|
| D1 | 项目目录名 vs 显示名 | **分离**：目录 ASCII slug，中文放 `name`（灵文已实践） |
| D2 | Claude Code 类外挂 | **有源码** + `origin:attached`；Butler 不控 IDE 进程 |
| D6 | 分类是否四档来源 | **否**；主类仅 **有/无源码**，来源用 tags |
| D3 | 测试默认通道 | 微信：**runtime readonly job** 优先于开 Lead terminal |
| D4 | 灵文完结后是否改 state | **不改**历史 state；用 `lifecycle: complete` 驱动话术 |
| D5 | 新建项目是否默认 Lead | **否**；仅 `novel-factory*` / 显式 `lead: true` |

---

## 9. 相关文档

- [`projects/README.md`](../../projects/README.md)
- [`projects/LingWen1/docs/pilot-setup.md`](../../projects/LingWen1/docs/pilot-setup.md)
- [`projects/LingWen1/docs/project-lead-scope.md`](../../projects/LingWen1/docs/project-lead-scope.md)
- [`guides/wechat-daily-smoke-checklist.md`](../guides/wechat-daily-smoke-checklist.md)
