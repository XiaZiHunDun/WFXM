# Butler v4 × agency-agents 提炼分析报告

> **日期**：2026-05-25  
> **对照代码**：`butler/`（v4 架构）、`reference/agency-agents/`（外部参考，gitignore）  
> **原则**：只借鉴设计与 Prompt 资产，**零新增运行时 pip 依赖**；不替代自建 Loop / 微信 Gateway  
> **相关文档**：[`v4-architecture.md`](../../architecture/v4-architecture.md) · [`reference-learning-plan-2026-05.md`](../archive/reference-learning-plan-2026-05.md) · [`cc-butler-gap-analysis-2026-05.md`](../active/cc-butler-gap-analysis-2026-05.md)

---

## 1. 执行摘要

**agency-agents** 是一套约 **189** 个 Markdown 专家人格 + **NEXUS** 多 Agent 编排教义（阶段门控、Dev↔QA 循环、标准化 Handoff），**不含可执行运行时**。

**Butler v4** 是完整的 Agent 平台（自建 Loop、工具、DAG 编排、微信 Gateway、上下文经济学）。

**结论**：agency-agents **不能**替代 Butler 运行时；其价值在于 **垂直专家知识、编排协议、QA 纪律、工作流模板**。应提炼为 Butler 的 **Skill 库 / agent profile 增强 / workflow YAML / 委派上下文协议**，而非新建 189 个 Agent 角色。

---

## 2. 两套系统本质差异

| 维度 | Butler v4（WFXM） | agency-agents（reference） |
|------|---------------------|----------------------------|
| 形态 | 可执行运行时：Loop、Gateway、真实工具 | Prompt/Skill 资产库 + NEXUS 文档编排 |
| Agent 粒度 | 3 角色：`dev` / `content` / `review`（`butler/agent_profiles.py`） | 14 事业部、上百垂直专家 |
| 编排 | 代码级 DAG：`TaskOrchestrator` + `WorkflowRunner` + `delegate_task` | 文档级：7 阶段流水线、Dev↔QA、handoff 模板 |
| 质量闭环 | `AgentReport`、`human_gate`、工具 guardrails | 证据优先 QA + PASS/FAIL 模板 + 最多 3 次重试 |
| 分发 | `skills_list` / `skill_view`、项目注册表 | `convert.sh` → Cursor / Claude Code / OpenCode 等 |

### Butler 代码入口（事实来源）

| 场景 | 路径 |
|------|------|
| Agent 主循环 | `butler/core/agent_loop.py` |
| DAG 编排 | `butler/task_orchestrator.py` |
| Workflow | `butler/workflows/runner.py`、`butler/workflows/schema.py` |
| 委派 | `butler/tools/registry.py`（`delegate_task`） |
| 角色 | `butler/agent_profiles.py` |
| 委派预设 | `butler/delegate_categories.yaml` |
| 人工门控 | `butler/human_gate.py` |

### agency-agents 关键资产

| 资产 | 路径 |
|------|------|
| 专家 roster | `reference/agency-agents/{engineering,testing,marketing,...}/*.md` |
| NEXUS 总纲 | `reference/agency-agents/strategy/nexus-strategy.md` |
| 阶段 Playbook | `reference/agency-agents/strategy/playbooks/phase-*.md` |
| Handoff 模板 | `reference/agency-agents/strategy/coordination/handoff-templates.md` |
| 激活 Prompt | `reference/agency-agents/strategy/coordination/agent-activation-prompts.md` |
| 元编排 | `reference/agency-agents/specialized/agents-orchestrator.md` |
| 工具链 | `reference/agency-agents/scripts/convert.sh`、`lint-agents.sh` |

---

## 3. agency-agents 可提炼的核心能力

### 3.1 NEXUS 编排模型

NEXUS 针对多 Agent 协作的失效模式：

- **阶段门控**：Phase 0→6，阶段间须过 quality gate
- **Dev↔QA 微循环**：实现 → Evidence Collector → PASS 才下一任务；FAIL 且 attempt < 3 则带反馈重试
- **标准化 Handoff**：元数据、交付物、验收标准、证据要求
- **激活 Prompt 模板**：角色占位符化启动指令
- **任务分配矩阵**：任务类型 → Primary Dev → Backup → QA（见 `phase-3-build.md`）

### 3.2 专家文档结构

- YAML frontmatter：`name`、`description`、`color`（`lint-agents.sh` 校验）
- 章节：Identity、Core Mission、Critical Rules、清单与可执行步骤
- 强人格与反模式（如 Evidence Collector：默认找 3–5 个问题、无截图不算完成）

### 3.3 元角色

- **Agents Orchestrator**：PM → Architect → Dev↔QA → Integration 总控
- **Workflow Architect**：实现前画清分支、失败恢复、handoff 契约（spec 向，不写代码）

### 3.4 工程化工具链

- 一套源 → 多 IDE 格式（含 Cursor `.mdc`）
- Agent 文档 lint
- 中文 i18n（`scripts/i18n/`）

### 3.5 与 WFXM 相关的垂直专家（优先导入候选）

- `engineering-wechat-mini-program-developer`
- `engineering-code-reviewer`、`engineering-technical-writer`
- `testing-evidence-collector`、`testing-reality-checker`
- 营销：微信公号、抖音、小红书、B 站等
- `specialized/agents-orchestrator.md`

---

## 4. Butler 已具备、不必从 agency 重造的能力

以下 Butler **已用代码实现**；agency 仅有文字流程：

- 上下文经济学：压缩、spill、分级剪枝、post-compact、`reactive_compact`
- 真实工具与权限：`permissions.yaml`、read-before-edit、terminal/git 门控
- 委派运行时：`cache_safe_delegate`、深度限制、异步委派、`AgentReport` 回传
- Gateway：入站队列、流式出站、会话注册
- 可观测：`runtime_metrics`、`/诊断`
- 业务 workflow：如 `butler/workflows/builtin/novel-factory.yaml`

### Butler 已有、但与 NEXUS 存在差距的点

| 能力 | Butler 现状 | agency/NEXUS |
|------|-------------|--------------|
| Workflow 重试 | `TaskNode.max_retries` 默认 **1** | Dev↔QA 默认 **3** 次再升级 |
| Handoff | `context` 自由文本 | 结构化 Metadata + Acceptance + Evidence |
| 专家库 | 3 个 `agent_profiles` | 189 个垂直人格 |
| Review 纪律 | 通用审核 prompt | Evidence-first、PASS/FAIL 机器可读 |
| 路由 | 手动选 role/category | 任务类型 → Dev/QA Skill 矩阵 |

---

## 5. 提炼优化项（按优先级）

### P0 — 低成本、高收益

#### ① agency 专家库 Skill 化

- 一次性导入：agency `.md` → `butler/registry/catalog/skills/` 或项目 `.butler/skills/`
- 执行仍用 **3 个 role**；通过 `skill_view` / `inject_skill_context` 加载专家正文
- **不要** 为 189 个角色各建 `agent_profiles` 与独立模型配置

#### ② Dev↔QA workflow 模板

新增 builtin workflow（如 `dev-qa-loop.yaml`）：

- `implement`（dev）→ `qa`（review，`depends_on`）
- QA 步骤要求 NEXUS 式 PASS/FAIL + 可核对证据
- **透传** `max_retries`：workflow step → `TaskNode`（当前 `WorkflowStepDef` 无此字段）

#### ③ 委派类别与 NEXUS 模式对齐

扩展 `delegate_categories.yaml`：

- `nexus-sprint`：实现 + 审查串联提示
- `nexus-micro`：单步 + Evidence 检查清单

在 `prompt_append` 嵌入 Activation Prompt 关键段（任务 ID、验收标准、禁止 scope creep）。

#### ④ Evidence-first 审查纪律

从 `testing-evidence-collector.md` 提炼进 `review_agent` 或独立 Skill：

- 首次实现默认预期 ≥3 项可改进点
- 完成声称前须有 pytest/diff/`read_file` 等证据
- 结构化 PASS/FAIL 便于主 Agent 决定是否重试

---

### P1 — 中等投入

#### ⑤ Handoff 上下文协议

在 `delegate_task` / workflow `context` 约定块字段：

| 字段 | 含义 |
|------|------|
| `from_role` / `to_role` | 交接双方 |
| `current_state` | 已完成项 |
| `deliverable` / `acceptance[]` | 交付与验收 |
| `evidence_required` | 证据类型 |
| `relevant_files[]` | 相关路径 |

实现建议：`workflows/variables.py` 或 `delegate_context.py` 增加 `render_handoff()`，从上一步 `AgentReport` / `var_pool` 填充。

#### ⑥ 任务分配矩阵 → `delegate_routing.yaml`

将 `phase-3-build.md` 矩阵压缩为路由表：`match` 关键词 → `role` + `skill` + `qa_skill`；主 Agent 或 `/workflow` 选型，**执行仍三角色**。

#### ⑦ Orchestrator Skill（仅主 Butler）

导入 `agents-orchestrator.md` 为管家可见 Skill：何时 `run_workflow`、如何拆 sprint、何时 `human_gate`。

#### ⑧ Skill/Agent 文档 lint

借鉴 `lint-agents.sh`，在 registry CI 校验 frontmatter 与推荐章节。

#### ⑨ 三档交付模式

| NEXUS 模式 | Butler 映射 |
|------------|-------------|
| Micro | `delegate category: quick` + 单次 review |
| Sprint | `dev-qa-loop` + 短 DAG |
| Full | 多 workflow + `human_gate` 阶段确认 |

---

### P2 — 按产品需要

- Phase Playbooks → `docs/templates/workflows/` YAML 草案
- Workflow Architect + `workflows/validate.py`：长流程上线前 spec 门禁
- Cursor：精选专家 → `.cursor/rules/`（IDE 开发体验，非 Gateway）
- 中国区营销 Skill 包 → `content_agent` 按需加载

---

## 6. 明确不照搬项

| agency 做法 | 不采纳原因 |
|-------------|------------|
| 189 个独立运行时 Agent | 成本、权限体系、与三角色架构冲突 |
| bash `spawn` 串流程 | Butler 已有 `TaskOrchestrator` |
| Playwright 截图硬编码为默认 QA | 需终端/环境；应 Optional Skill |
| 完整 NEXUS-Full 12–24 周流水线 | 超出微信管家产品边界；仅作模板库 |
| 运行时依赖 agency 仓库 | `reference/` gitignore；内容须拷贝进 `butler/registry` 或 docs |

---

## 7. 目标架构（提炼后）

```text
用户 (微信/CLI)
    │
    ▼
Butler 主 Loop ──skill_view──► agency 提炼 Skill 库（按任务路由）
    │
    ├─ delegate_task(category=nexus-*) + handoff 块
    │
    └─ run_workflow(dev-qa-loop)
              │
              ├─ dev_agent (+ 领域 skill，如 frontend-developer)
              └─ review_agent (+ evidence-collector skill)
                    max_retries=3 → TaskOrchestrator
```

---

## 8. 建议实施顺序

1. 导入脚本 + 精选 **15–25** 个 Skill（工程、QA、微信/内容、orchestrator）
2. `dev-qa-loop` builtin workflow + workflow `max_retries` 透传
3. Handoff 中文模板 + `review_agent` 证据纪律
4. `delegate_routing.yaml` + category 预设
5. registry lint + 本报告落地后的实现 PR（保持零新 pip 依赖）

---

## 9. 文档维护

若落地 P0+ 项，请同步：

- [`docs/architecture/v4-architecture.md`](../../architecture/v4-architecture.md)（Skill 导入、workflow 名）
- [`docs/plans/README.md`](README.md)（规划索引一条）
- 可选：[`CONTRIBUTING.md`](../../../CONTRIBUTING.md)（推荐 workflow / delegate category）

---

## 10. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：Butler v4 与 agency-agents 对照及提炼路线图 |
