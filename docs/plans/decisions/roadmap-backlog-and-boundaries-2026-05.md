# 路线图 — 未做、边界与可选 Backlog（2026-05）

> **状态**：Agent / 规划 **决策入口**（2026-05-25）  
> **用途**：合并各优化路线图、对照报告中的「不做」「未排期」「深化边界」「可选立项」，避免重复检索与误判「功能缺失」。  
> **勿用**：`docs/history/`、各报告全文中的旧 P0/P2 表当作当前待办。

---

## 0. 30 秒决策流

```text
新需求
  ├─ 命中 §1 否决？ ──是──► 拒绝或改产品边界（勿立项）
  ├─ 命中 §2 深化边界？ ──是──► 说明已有子集 + 缺口（§4 速查）
  ├─ 属 §3 可选 Backlog？ ──是──► 单独立项 + 验收标准
  └─ 否则 ──► 在现有 Loop/Gateway/工具上扩展（见 v4-architecture）
```

| 我想… | 读这里 |
|--------|--------|
| **否决 / 不做** | 本文 **§1** |
| **接开源 / MCP / 外购能力** | [`extension-rd-loop-2026-06.md`](../active/extension-rd-loop-2026-06.md) |
| **报告写「未做」但可能已有** | 本文 **§2** + §4 速查 |
| **真要排期新功能** | 本文 **§3**（含 **§3.6 产品立项**） |
| **查已落地能力** | 本文 **§4** |
| **Dev 能力上限 / 对标 CC CLI** | [`dev-capability-ceiling-vs-cc-cli-2026-06.md`](dev-capability-ceiling-vs-cc-cli-2026-06.md) |
| **四报告 18 项详情** | [`four-reports-out-of-scope-2026-05.md`](../decisions/four-reports-out-of-scope-2026-05.md) |
| **五报告 S1–S11 原文** | [`five-reports-improvement-roadmap-2026-05.md`](../roadmaps/five-reports-improvement-roadmap-2026-05.md) §6 |

---

## 1. 否决（产品边界 — 勿立项）

除非 **书面变更产品边界**，下列能力 **不实现**。裁决优先级：**§1.1 四报告** 与 **§1.2 五报告** 并列；Hermes/LangChain 等平台级否决见 **§1.3**。

### 1.1 四报告否决（18 项）

完整原因、替代方案、报告索引见 **[`four-reports-out-of-scope-2026-05.md`](../decisions/four-reports-out-of-scope-2026-05.md) §2**。

| 域 | 代表项 | Butler 替代 |
|----|--------|-------------|
| 浏览器 | CDP/DOM/截图 Loop、视觉逐步驱动 | `web_fetch`、`terminal` |
| RAG 平台 | RAGFlow 全栈、Studio、MinerU/Docling 全家桶 | `semantic_index` + `chunking` + `butler memory search` |
| 设计标本 | 73 套 DESIGN 进主仓、Stitch 流水线、设计 Agent 替代 Loop | 项目 `DESIGN.md` + `design_md_sections` + `ui-build` |
| 实验自治 | 通宵 NEVER STOP、无门控每轮 git commit/reset | `goal_loop` 默认关；`experiment` CLI 显式开关 |
| 检索/观测 | LLM 子 query 分解、LangSmith 默认 APM | 启发式 `query_decompose`；`runtime_metrics` + `/诊断` |

### 1.2 五报告否决（S1–S11）

来源：[`five-reports-improvement-roadmap-2026-05.md`](../roadmaps/five-reports-improvement-roadmap-2026-05.md) §6。

| # | 能力 | 来源 | 原因 | Butler 替代 |
|---|------|------|------|-------------|
| S1 | claude-mem **Bun Worker + Chroma MCP** | claude-mem | 运行时/依赖栈不符 | `semantic_index` + workspace `.butler/observations.db` |
| S2 | claude-mem **IDE 插件 / Viewer UI** | claude-mem | 入口是微信 | CLI / 微信命令 |
| S3 | CC Switch **Tauri 桌面 + 托盘** | cc-switch | 非服务端产品 | CLI + 微信 `/诊断` |
| S4 | CC Switch **五 CLI live 配置双向同步** | cc-switch | 维护面过大 | `project.yaml` + 原子写 |
| S5 | CC Switch **内置 HTTP 代理全家桶** | cc-switch | 网络中间层越界 | 薄 MCP + 现有 transport |
| S6 | PEG **LangChain Agent / notebook 运行时** | PEG | 教学标本 | 自建 `agent_loop` + prompt |
| S7 | PEG **ToT / APE 全自动 prompt 搜索** | PEG | 成本不可控 | `butler prompt eval` + 人工改 prompt |
| S8 | TradingAgents **LangGraph + 行情 API** | tradingagents | 领域/依赖越界 | `task_orchestrator` + workflow YAML |
| S9 | TradingAgents **SQLite checkpoint 进 core** | tradingagents | 与 transcript 策略冲突 | `session_transcript` + 人工门控 |
| S10 | LobeHub **浏览器 Agent Loop / Chat UI** | lobehub | 产品形态不同 | 微信 Gateway + Butler Loop |
| S11 | LobeHub **全量 MCP Host + OTEL 默认** | lobehub | 重依赖 APM | `BUTLER_MCP_ENABLED` 薄客户端 + `runtime_metrics` |

### 1.3 外部对标平台级否决（Hermes / LangChain / Dify / Langflow）

来源：[`../guides/external-reference-deferred-2026-05.md`](../../guides/external-reference-deferred-2026-05.md) §3。

| 能力 | 原因 |
|------|------|
| Hermes 单体 Loop / 多平台网关 | 违背 v4 架构 |
| LangChain + LangGraph **替换** `agent_loop` | 维护与产品边界 |
| Dify GraphEngine / Celery / plugin_daemon | 非微信管家 |
| Langflow 画布 / Flow JSON 一等公民 | 无 Studio |
| workflow 暂停后 **自动续跑** | 维持显式 `/workflow` |
| SQL 消息库 **替换** `transcript.jsonl` | JSONL + 索引够用 |
| 多租户 SaaS / 计费 | 产品边界 |
| MCP Host 全家桶 / 浏览器自动化平台 | 见 §1.1、S11 |

---

## 2. 深化边界（已有子集 — 勿报「未实现」）

下列项在各路线图 P2/对照报告中常标「未做」，但 **仓库已有可开关子集**。缺口是「全量对标」，不是「零实现」。

### 2.1 五报告主线（PR-F1–F6 + P5–P10）

| 路线图表述 | 当前子集 | 速查 |
|------------|----------|------|
| CC Switch 级 IDE/托盘 | `/预设`、`provider apply`、`/模型 preset` | [`external-agent-reports-capabilities-2026-05.md`](../../guides/external-agent-reports-capabilities-2026-05.md) |
| APE / ToT 全自动 prompt | `butler prompt eval` pattern + `--llm` + corpus live | 同上 + `./scripts/butler-five-reports-gate.sh` |
| LangGraph 级 Bull/Bear | 可选 `trading-debate` workflow（非默认微信） | `butler/workflows/builtin/trading-debate.yaml` |
| 全量 Pydantic 终局树 | `output_schema_registry` + 多轮 repair | `BUTLER_OUTPUT_SCHEMA_REPAIR_MAX` |
| npm 级 MCP Host | 薄 MCP + deferred + SSOT + 安装前扫描 | `BUTLER_MCP_ENABLED`、`butler mcp scan` |
| Hub 市场 manifest 全量 | `registry verify` + `BUTLER_MCP_CATALOG_URLS` 远程合并 | `butler registry verify` |
| Thinking 协议全自动 beta 矩阵 | `BUTLER_THINKING_PROTOCOL` + `thinking_headers` | `BUTLER_THINKING_BETA_*` |
| Injection human_gate | `BUTLER_INJECTION_LLM_GATE` | 微信确认 + 重发 |

**P5–P10 批次清单**见 [`five-reports-not-done-2026-05.md`](../decisions/five-reports-not-done-2026-05.md) §3（与本文同步）。

### 2.2 外部 Agent 主线（PR-X1–X6）

| 主线 | 路线图 P2 级「未做」常见项 | 已落地子集 |
|------|---------------------------|------------|
| **K** 协议 | 全量 dataset_info、plugins 深合并 | `message_ir`、`tool_wire`、`project_plugins` |
| **L** Harness | LangGraph checkpoint、Docker Sandbox | skill rescue、MCP deferred、`ask_clarification` |
| **M** 确认 | Docker/E2B、Browser、React GUI | 两阶段确认、STUCK、session initializing |
| **N** MetaGPT | Team/Environment、AFlow/SPO | exp_cache、BM25 recall、schema 校验 |
| **O** Ansible | Worker 池、Jinja 全生态 | rescue/optional、serial、import_workflow 子集 |

核对表：[`external-agent-reports-improvement-roadmap-2026-05.md`](../roadmaps/external-agent-reports-improvement-roadmap-2026-05.md) §10。

### 2.3 四报告 / Sprint / OpenCode

| 来源 | 「未做」表述 | 实际 |
|------|--------------|------|
| 四报告 RF-P2 | 目录 watch + MinerU 全家桶 | **不做**（§1.1）；轻量 reindex 已有 |
| Gemini 对照 G-P1+ | 多项 CLI 能力 | **defer**，非 blocking |
| OpenCode 对照 P2/P3 | SQLite 全量、LSP、Share URL | **暂缓/不做**；见 [`opencode-butler-comparison-report-2026-05.md`](../comparisons/opencode-butler-comparison-report-2026-05.md) |
| OpenCode learning plan | SQLite 全量模型 | **仍暂缓** |

### 2.4 Dev 能力（勿报「达不到 Cursor」）

| 常见误判 | 实际 |
|----------|------|
| 「Dev 要对标 Cursor IDE Agent」 | **不对标**；IDE 层（LSP、内联 diff）非 Butler 形态 |
| 「Dev 达不到顶级 coding agent」 | 应对标 **Claude Code CLI**；Loop 层 CC 线束已收口 |
| 「必须无限制 shell 才算 dev」 | **产品否决**；见 dev profile 白名单 + 委派 |
| 「需要 Docker 会话沙箱才算隔离」 | **产品否决**；Linux **terminal bubblewrap**（`BUTLER_TERMINAL_SANDBOX`）+ 应用层门控为上限；见 `v4-architecture.md` §执行隔离 |

**SSOT**：[`dev-capability-ceiling-vs-cc-cli-2026-06.md`](../decisions/dev-capability-ceiling-vs-cc-cli-2026-06.md)

### 2.5 依赖分层 / 本地状态（外部依赖策略）

| 常见误判 | Butler 现行策略 |
|----------|-----------------|
| “要补 Redis / Postgres / MQ 才算完整 Agent 平台” | **不需要**；继续走 `transcript.jsonl` + 文件状态 + SQLite 派生索引 |
| “SQLite 已引入，就该替换 transcript 为 SQL 会话库” | **不做**；SQLite 只用于 `observations.db`、tail/read model 等查询层 |
| “新增能力应直接进 core 默认依赖” | **不建议**；微信/MCP/voice/OCR/PTY 等优先走 `optional-dependencies` |
| “出站可靠性需要外部 broker” | **不需要**；优先本地 durable outbox + `runtime/push_queue.jsonl` 重试 |

---

## 3. 可选 Backlog（可单独立项）

**不属于否决**，也 **未承诺排期**。立项时需写验收标准与 `BUTLER_*` 开关。

### 3.0 扩展选型与接入（Extension R&D Loop）

**规程 SSOT**：[`active/extension-rd-loop-2026-06.md`](../active/extension-rd-loop-2026-06.md)

- **原则**：Loop/Gateway/记忆自建；长尾能力 **MCP → optional-extra → builtin（最后）**  
- **闭环**：Observe → Research → Decide（Owner）→ Integrate（opt-in）→ Verify → Track  
- **2026-Q3 首批试点**：EXT-1 ✅ · EXT-2 ✅ · EXT-3 ✅ · **EXT-4 ✅**（[GitHub OpenAPI](../active/extension-candidates/ext-4-second-openapi-2026-06.md)，2026-06-22 Verify）  
- **2026-Q4 推荐**：EXT-5 MarkItDown MCP **Integrate ✅** · Verify sim ✅（[一页纸](../active/extension-candidates/ext-5-markitdown-mcp-2026-06.md) · [真机验收](../guides/ext5-wechat-verify-2026-06.md)）
- **Agent 可** 起草选型一页纸；**不可** 无人值守改 core 依赖或绕过白名单

### 3.1 安全 / 凭证 / 网关

| 项 | 来源 | 说明 |
|----|------|------|
| `secrets.yaml` **Fernet 加密** | Dify 对标 | ✅ `BUTLER_SECRETS_ENCRYPT` + `butler secrets encrypt`（2026-06 P2-03） |
| `execute_code` 生产开放 | Hermes | 默认 `BUTLER_EXECUTE_CODE=0`；须安全评审 |
| 微信真·流式**编辑**回复 | Hermes | 依赖 iLink 能力；现有 progressive 为补充消息 |
| 权限 **LLM 分类器** | Hermes | 与「无 classifier」原则冲突 |

### 3.2 检索 / 工具 / 协议

| 项 | 来源 | 说明 |
|----|------|------|
| 全量 RAG **ingest 管线** | Dify | 已有 search；ingest 另立项 — **规程** [`extension-rd-loop` §5 EXT-3](../active/extension-rd-loop-2026-06.md) |
| OpenAPI 声明式 HTTP 工具 | Dify | EXT-2 Todoist + **EXT-4 GitHub** ✅；下一模板见 EXT-6 季度评审 |
| LLM 工具模拟器 | LangChain | 仅测试路径，ROI 低 |
| LangChain **Checkpointer** 断点续跑 | LangChain | 单进程微信非刚需 |
| **corpus live 全量**（非 smoke） | PEG | 成本高；已有 `--corpus-live-full` 上限子集 |

### 3.2.1 Observation Store 残留项（开发完成后统一收口）

| 项 | 来源 | 说明 |
|----|------|------|
| `observations.tsv` -> `observations.db` 一次性迁移 | SQLite observation store 首版 | ✅ `observation_migrate.py` + `butler memory observations --migrate` |
| observation 路径历史排序/权重优化 | SQLite observation store 收口 | 当前以最近命中为主（文档化）；工具/成功率权重仍 Backlog |
| observation 导出/诊断命令 | SQLite observation store 收口 | ✅ `/诊断 详细` + `butler memory observations` |

### 3.3 OpenCode 净新增（P2/P3）

见 [`opencode-butler-comparison-report-2026-05.md`](../comparisons/opencode-butler-comparison-report-2026-05.md)「仍明确暂缓」与 P2/P3 表：Compaction 一等任务、异步委派通知、worktree 会话、LSP、Share 公网 URL、Post-edit format 等。

### 3.4 产品运营（post-consolidation）

见 [`post-consolidation-roadmap-2026-05.md`](../active/post-consolidation-roadmap-2026-05.md) 轨道 A–D **未完成项**（灵文运营、Git 项目注册、识图 P3、主机工具白名单等）。与对标路线图 **正交**。

### 3.5 仓库 / 双实例（整理备忘）

见 [`p3-deferred-deep-dive-2026-05.md`](../archive/p3-deferred-deep-dive-2026-05.md)（双实例、记忆排查 — **非**五报告 P3）。

### 3.6 产品评估立项（2026-06 — P0/P1 带验收）

> **来源**：产品向评估（2026-06-25）；与 [`butler-system-assessment-and-ops-2026-06.md`](butler-system-assessment-and-ops-2026-06.md)、[`agent-testing-strategy-2026-06.md`](agent-testing-strategy-2026-06.md) 对齐。  
> **原则**：不重复 §1 否决；在现有 Loop/Gateway/脚本上扩展；每项须可验收、可链到守门脚本。  
> **状态**：`backlog` = 未承诺排期；`in_progress` / `done` 在变更记录或 `pilot-log` 打卡。

#### 总览

| ID | 优先级 | 名称 | 建议周期 | 状态 |
|----|--------|------|----------|------|
| [PROD-P0-01](#prod-p0-01-g1-04-ot2-观测与-owner-硬反馈) | P0 | G1-04 OT2 观测与 Owner 硬反馈 | 2–4 周 | **done** 2026-06-26 |
| [PROD-P0-02](#prod-p0-02-配置剖面产品化) | P0 | 配置剖面产品化 | 2–4 周 | **done** 2026-06-26 |
| [PROD-P0-03](#prod-p0-03-pytest-技术债与-gate-叙事统一) | P0 | pytest 技术债与 gate 叙事统一 | 2–4 周 | **done** 2026-06-26（叙事+bisect 记录；全量修债 backlog） |
| [PROD-P1-01](#prod-p1-01-dev-委派-verify-与-lead-门控) | P1 | Dev 委派 verify 与 Lead 门控 | 1–2 月 | **done** 2026-06-22 |
| [PROD-P1-02](#prod-p1-02-owner-默认路径简报--onboarding) | P1 | Owner 默认路径（简报 + onboarding） | 1–2 月 | **done** 2026-06-26 |
| [PROD-P1-03](#prod-p1-03-记忆月度探针运营化) | P1 | 记忆月度探针运营化 | 1–2 月 | **done** 2026-06-25 |
| [PROD-P2-01](#prod-p2-01-wechat_ilink-结构拆分) | P2 | `wechat_ilink` 结构拆分 | Backlog | **done** 2026-06-25 |
| [PROD-P2-02](#prod-p2-02-observation-store-收口) | P2 | Observation Store 收口 | Backlog | **done** 2026-06-22 |
| [PROD-P2-03](#prod-p2-03-安全信任补丁批次) | P2 | 安全信任补丁批次 | Backlog | **done** 2026-06-22 |
| [PROD-P2-04](#prod-p2-04-extension-ext-4) | P2 | Extension EXT-4+ 选型 | 季度 | **done** 2026-06-22 |

**建议执行顺序（开发会话对齐）**：

```text
本周     PROD-P0-02（文档+诊断首屏）· PROD-P0-03（叙事/issue）· PROD-P0-01（/诊断 G1-04 面）
本月     PROD-P1-03 done 2026-06-25；P1 线收束
窗满     PROD-P0-01 结案：butler-g1-04-closure-check.sh → 更新 gap register
Backlog  PROD-P2-01 … P2-04（与发版节奏穿插）
```

---

#### PROD-P0-01：G1-04 OT2 观测与 Owner 硬反馈

| 字段 | 内容 |
|------|------|
| **问题** | 窗 **06-09→07-31** 内已有大量 `prod_delegate_*` 自动记账，但 **Owner 显式纠正路径缺失**；`/诊断` 简要面未展示 OT2 进度；窗满前易误判「已闭环」。 |
| **范围（做）** | Owner 硬反馈入口；`/诊断` 简要 + `/doctor` 展示 `g1_04_observation_window_status`；窗满结案与登记册同步 |
| **范围（不做）** | 替换 `eval_feedback` 管线；LangFuse 全量 APM；自动改 prompt/权重 |

**验收标准**

1. **可见性**：微信 `/诊断`（非 `详细`）首屏含 **OT2 观测** 块：`窗剩余天数`、`窗内条数`、`生产/B9` 分类、`ot2_closure_ready` 人话（是/否/窗未满）。
2. **Owner 硬反馈**：至少一种微信可触发路径写入 `eval_feedback`，`evidence=production`，`trigger` **非** `prod_delegate_*` / `b9_*`（例：`/反馈 不对 …`、`/验收 驳回 …` 或等价 slash）；含 owner-gate。
3. **自动证据保持**：`BUTLER_EVAL_PROD_EVIDENCE=1` 时委派 verify 仍写 `prod_delegate_verify_pass` / `prod_delegate_failure`（不回归）。
4. **运维脚本**：`bash scripts/butler-g1-04-closure-check.sh` 窗未满 **exit 2** 为预期；`bash scripts/butler-dev-prod-evidence-checklist.sh` 输出与 `/诊断` 一致。
5. **窗满结案**（07-31 后）：`ot2_closure_ready=true` 时 `butler-g1-04-closure-check.sh` **exit 0**；[`theory-implementation-gap-register-2026-06.md`](theory-implementation-gap-register-2026-06.md) G1-04 行更新为 ✅。
6. **测试**：`tests/ops/test_g1_04_prod_evidence.py` 扩展；Owner 反馈 handler 单测 ≥2。

**既有资产**

| 类型 | 路径 |
|------|------|
| 状态 API | `butler/ops/boundary_observability.py` → `g1_04_observation_window_status` |
| 自动生产证据 | `butler/ops/g1_04_prod_evidence.py` · `BUTLER_EVAL_PROD_EVIDENCE` |
| 脚本 | `scripts/butler-g1-04-closure-check.sh` · `scripts/butler-g1-04-weekly-checkin.sh` · `scripts/butler-dev-prod-evidence-checklist.sh` · `scripts/butler-ops-followup-check.sh` |
| 文档 | `docs/guides/evaluation-guide.md` · `docs/guides/phase4-ops-runbook.md` |

**运营节奏**：窗内 **每周** `butler-g1-04-weekly-checkin.sh`（含 closure-check + 证据清单 + `--log` 写 pilot-log）。

---

#### PROD-P0-02：配置剖面产品化

| 字段 | 内容 |
|------|------|
| **问题** | `.env.example` ~540 处 `BUTLER_*`；新 Owner 不知「生产微信机最少配什么」。 |
| **范围（做）** | 三剖面一页纸为**唯一推荐入口**；诊断/preflight 人话三档；与现有 `BUTLER_DEPLOY_PROFILE` / `BUTLER_ENV_PROFILE` 对齐 |
| **范围（不做）** | 删减 `reference.md`；新配置中心 UI |

**三剖面（SSOT 命名）**

| 剖面 | pip / 部署 | 终端 profile | 典型场景 |
|------|------------|--------------|----------|
| **gateway** | `BUTLER_DEPLOY_PROFILE=gateway` · `pip install -e ".[gateway]"` | — | 微信生产机 |
| **dev-local** | `BUTLER_DEPLOY_PROFILE=dev` | `BUTLER_ENV_PROFILE=dev-local` | 本机改 core + pytest |
| **dev-remote** | `gateway` + 项目 dev-remote | `BUTLER_ENV_PROFILE=dev-remote` | 远程沙箱 + CC 桥接 opt-in |

**验收标准**

1. **文档**：新增 `docs/guides/deploy-profiles-2026-06.md`（≤3 页），每剖面：**必填 env ≤10**、推荐脚本、`butler doctor` 期望；`README.md` / `AGENTS.md` 链到该文而非裸 `.env.example`。
2. **`/诊断` 简要**：根据 `BUTLER_DEPLOY_PROFILE` + 是否在跑 gateway，**只展示本剖面相关 5–8 项**（其余「展开：/诊断 详细」）。
3. **`butler project preflight`**：输出顶栏 **通过 / 需修复 / 可忽略** 三档摘要（≤5 行人话）；微信 `/项目` 或 preflight 子命令同文案（若已有 handler 则复用）。
4. **`butler doctor`**：增加 `deploy_profile` 与「偏离推荐剖面」警告（例：gateway 机装了 `dev` 但未跑 gateway）。
5. **守门**：`bash scripts/check-dead-env.sh` 仍绿；剖面文档中每条必填 env 在 `reference.md` 有对应行。

**既有资产**

| 类型 | 路径 |
|------|------|
| pip 剖面 | `BUTLER_DEPLOY_PROFILE` · [`dependency-terminology-2026-06.md`](../../guides/dependency-terminology-2026-06.md) §4 |
| 终端剖面 | `scripts/apply-butler-env-profile.py` · `BUTLER_ENV_PROFILE` |
| 运维 | `scripts/butler-gateway-ops.sh` · `scripts/butler-deploy.sh` · `scripts/setup-butler-config.sh` |
| 诊断 | `butler/cli/doctor.py` · `butler/gateway/owner_surface.py` |

---

#### PROD-P0-03：pytest 技术债与 gate 叙事统一

| 字段 | 内容 |
|------|------|
| **问题** | 全量 `pytest tests/` 约 **101 fail**（跨测状态泄漏，`test_tools_registry` 等）；分层 gate 绿 → 两套叙事并存。 |
| **范围（做）** | 文档明确发版 gate；bisect 根因或隔离泄漏；可选 CI 只跑分层 |
| **范围（不做）** | 以全量 pytest 为唯一发版门槛（见 §1 评估「勿双标」） |

**验收标准**

1. **叙事**：`README.md` · `CONTRIBUTING.md` · [`agent-testing-strategy-2026-06.md`](agent-testing-strategy-2026-06.md) 含 **gate 矩阵表**（PR / 发版 / 月度 / 全量各自跑什么）。
2. **根因**：`pilot-log` 或 issue 记录 bisect 结论（泄漏模块列表 + 修复 PR 或 `xfail` 理由）。
3. **目标**：全量 fail **≤10** 或明确标注 `pytest tests/ -q` 为 **maintainer optional** 且 CI 不跑。
4. **守门不变**：`bash scripts/butler-pytest-fast-gate.sh` · `butler-pre-release-smoke.sh` 仍绿。

**既有资产**

| 类型 | 路径 |
|------|------|
| 策略 SSOT | [`agent-testing-strategy-2026-06.md`](agent-testing-strategy-2026-06.md) |
| Fast gate | `scripts/butler-pytest-fast-gate.sh` |
| 记录 | `projects/LingWen1/docs/pilot-log.md` §pytest 技术债 |

---

#### PROD-P1-01：Dev 委派 verify 与 Lead 门控

| 字段 | 内容 |
|------|------|
| **问题** | 头对头仍慢于 CC CLI；VERIFY 命令靠 LLM 猜；Lead 场景偶发误委派。 |
| **范围（做）** | `project.yaml` 标准 `dev.*_command` 模板推广；`LEAD_READONLY_NO_DELEGATE` 评估默认化；B9/playbook 继续 |
| **范围（不做）** | CC 桥接立项（见 [`dev-cc-bridge-optional-2026-06.md`](dev-cc-bridge-optional-2026-06.md)）；对标 Cursor IDE |

**验收标准**

1. **模板**：`projects/DemoPilot/project.yaml` + `projects/LingWen1/project.yaml` 含非空 `dev.test_command` / `dev.lint_command`；新增 `docs/guides/project-yaml-dev-commands-template.md` 可复制段。
2. **VERIFY**：`butler/dev_engine/verify.py` 对两试点项目跑 delegate 后 **命中 project.yaml 命令**（单测或 `butler-pilot-dev-testing.sh` 日志可证）。
3. **Lead 门控**：`bash scripts/butler-wechat-lead-readonly-sim.sh` PASS；误委派话术返回 `LEAD_READONLY_NO_DELEGATE`。
4. **飞轮**：`bash scripts/butler-dev-flywheel-monthly.sh --log` 一月内 PASS；`pilot-log` 记录 T1/T4/T5 耗时对比（允许仍慢于 CC，但无 STUCK 回归）。
5. **SSOT 同步**：[`dev-capability-ceiling-vs-cc-cli-2026-06.md`](dev-capability-ceiling-vs-cc-cli-2026-06.md) P1 行标进展。

**既有资产**

| 类型 | 路径 |
|------|------|
| VERIFY | `butler/dev_engine/verify.py` |
| 门控 | `butler/tools/delegate_role_guard.py` |
| 脚本 | `scripts/butler-pilot-dev-testing.sh` · `scripts/butler-dev-flywheel-monthly.sh` · `scripts/butler-wechat-lead-readonly-sim.sh` |
| Playbook | `butler/dev_engine/prod_playbook_seeds.py` |

---

#### PROD-P1-02：Owner 默认路径（简报 + onboarding）

| 字段 | 内容 |
|------|------|
| **问题** | 数十条微信命令分散；缺「我今天该看什么」默认路径。 |
| **范围（做）** | `/简报` 四块固定；首次绑定 onboarding 三步；长回复摘要与 `/详细`+附件 协同 |
| **范围（不做）** | 新 GUI；全量命令重命名 |

**验收标准**

1. **`/简报`**：固定顺序四块 — **待办 / 队列 / 门控 / 昨夜 job**（标题可微调，块序不变）；其余折叠为「更多：/高级」。
2. **Onboarding**：`BUTLER_ONBOARDING_WELCOME=1` 时首会话 **3 步引导**文案：切换项目 → 只读一句 → 试一次委派（链 `wechat-core-scenario.md`）。
3. **长回复**：`BUTLER_TURN_SUMMARY_LINE` 生产默认开；附 `.txt` 时聊天气泡受 `BUTLER_WECHAT_ATTACH_BRIEF_CHARS` 限制（**done** @ `4f01d23`）。
4. **sim**：`bash scripts/butler-wechat-owner-sim.sh --track owner-ux` PASS；`/简报` case 断言四块关键词。
5. **真机**：`wechat-daily-smoke-checklist.md` 增 1 行 onboarding + 简报块序勾选。

**既有资产**

| 类型 | 路径 |
|------|------|
| 简报 | `butler/gateway/owner_surface.py` · slash handlers |
| Welcome | `butler/gateway/handler_helpers.py` · `BUTLER_ONBOARDING_WELCOME` |
| 附件 brief | `butler/gateway/wechat_text_export.py` |
| 剧本 | [`wechat-core-scenario.md`](../../guides/wechat-core-scenario.md) |
| sim | `.butler/simulation/wechat-owner-scenarios.yaml` track `owner-ux` |

---

#### PROD-P1-03：记忆月度探针运营化

| 字段 | 内容 |
|------|------|
| **问题** | `butler-memory-phase-a/b.sh` 自动化绿，灵文 `memory-guide` M1–M7 真机表仍有未勾项。 |
| **范围（做）** | 5 分钟月度话术 + 固定脚本；结果写 `pilot-log` |
| **范围（不做）** | 新记忆算法 |

**验收标准**

1. **脚本**：`bash scripts/butler-memory-monthly-probe.sh`（或扩展现有 `butler-memory-phase-b.sh --monthly-log`）exit 0，输出 M1–M7 逐项 ✅/❌。
2. **文档**：[`memory-ops.md`](../../guides/memory-ops.md) 链到 **微信 5 分钟探针话术**（≤7 条 slash/自然语言）。
3. **运营**：`butler-dev-flywheel-monthly.sh` 或 ops follow-up **可选纳入**该探针；`pilot-log` 每月 1 行。
4. **与自动化一致**：探针 FAIL 时 phase-b 亦 FAIL（避免「脚本绿、运营红」）。

**既有资产**

| 类型 | 路径 |
|------|------|
| Phase A/B | `scripts/butler-memory-phase-a.sh` · `scripts/butler-memory-phase-b.sh` |
| 清单 | `projects/LingWen1/docs/memory-guide.md` · [`wechat-daily-smoke-checklist.md`](../../guides/wechat-daily-smoke-checklist.md) M1–M7 |
| 测试 | `tests/test_premise_memory_theory.py` · `tests/test_memory_metrics_benchmark.py` |

---

#### PROD-P2-01：`wechat_ilink` 结构拆分

| 字段 | 内容 |
|------|------|
| **问题** | `butler/gateway/platforms/wechat_ilink.py` ~1310 行，协议/推送/媒体改动牵一发动全身。 |
| **验收标准** | 按审计拆 `crypto/account/transport/adapter/media` 子包；**零行为变更**；现有 gateway pytest + `butler-wechat-attach-probe.sh` + 真机 smoke 绿；coverage 不下降。 |
| **来源** | [`project-deep-audit-2026-06.md`](../../reviews/project-deep-audit-2026-06.md) §2.1.1 |

---

#### PROD-P2-02：Observation Store 收口

见上文 **§3.2.1**；验收：TSV→DB 迁移脚本、`/诊断` 或只读命令可导出 observation 统计、PreRead 排序权重文档化。

| 字段 | 内容 |
|------|------|
| **状态** | **done** 2026-06-22 |
| **迁移** | `butler/memory/observation_migrate.py` · `scripts/butler-observation-migrate.sh` · 空 DB 首次打开自动导入 |
| **诊断** | `/诊断 详细` Observation Store 段 · `butler memory observations` |
| **文档** | [`observation-store-preread-2026-06.md`](../../guides/observation-store-preread-2026-06.md) |
| **测试** | `tests/test_observation_migrate.py` · `tests/test_observation_store.py` |

---

#### PROD-P2-03：安全信任补丁批次

见 **§3.1** 子集批次立项：PII 扩展、`secrets.yaml` Fernet、MCP SSRF 守门；每批 ≤5 项，附 `tests/` 与发版 note。

| 字段 | 内容 |
|------|------|
| **状态** | **done** 2026-06-22 |
| **PII** | `pii_scrub.py`：Bearer / AWS AKIA / GitHub PAT / 169.254 link-local |
| **Secrets** | `config_secrets_crypto.py` · `butler secrets encrypt` · `BUTLER_SECRETS_ENCRYPT*` |
| **MCP SSRF** | `validate_http_url` + `ipaddress` 字面量私网/metadata 拦截 |
| **文档** | [`trust-security-p2-batch-2026-06.md`](../../guides/trust-security-p2-batch-2026-06.md) |
| **守门** | `scripts/butler-trust-p2-gate.sh` · `tests/test_trust_p2_batch.py` |

---

#### PROD-P2-04：Extension EXT-4+

见 **§3.0** 规程；EXT-4 GitHub OpenAPI ✅；Q4 **EXT-5** 一页纸已起草（Decide 待 Owner）。

| 字段 | 内容 |
|------|------|
| **状态** | **done** 2026-06-22（选型闭环；EXT-5 Integrate 未开） |
| **EXT-4** | [ext-4-second-openapi-2026-06.md](../active/extension-candidates/ext-4-second-openapi-2026-06.md) · Verify ✅ |
| **季度评审** | [extension-quarterly-review-2026-06.md](../active/extension-quarterly-review-2026-06.md) |
| **EXT-5** | [ext-5-markitdown-mcp-2026-06.md](../active/extension-candidates/ext-5-markitdown-mcp-2026-06.md) · Integrate ✅ |
| **守门** | `scripts/butler-extension-ext4-gate.sh` |

### 3.7 产品体验 P3（Owner ROI — 2026-06）

> **来源**：Owner 产品评估（微信用户视角）；与 PROD-P1-02 正交，聚焦「少概念、多下一步」。

| ID | 名称 | 状态 |
|----|------|------|
| PROD-P3-01 | `/切换` slug 纠错 + Did-you-mean | **done** 2026-06-26 |
| PROD-P3-02 | 委派过程心跳 `DELEGATE_PROGRESS_NOTIFY` | **done** 2026-06-26 |
| PROD-P3-03 | 门控消息模板 + workflow 续跑提示 | **done** 2026-06-26 |
| PROD-P3-04 | 大改码 CC 路由建议（启发式） | **done** 2026-06-26 |
| PROD-P3-05 | Owner 首周 playbook | **done** 2026-06-26 |

守门：`bash scripts/butler-owner-ux-p3-gate.sh` · handler sim：`butler-owner-ux-p3-wechat-sim.sh` · 首周节奏：`butler-owner-week1-ops-sim.sh` · 文档 [`owner-first-week-2026-06.md`](../../guides/owner-first-week-2026-06.md)

---

**维护**：完成某项 → 本表 `状态` 改 `done`，摘要写入 §6 变更记录 + 相关 SSOT（`gap-register` / `pilot-log`）；部分交付可拆多 PR，但验收以本表勾选为准。

---

## 4. 已落地速查（勿当「未做」）

| 范围 | 文档 | 守门 |
|------|------|------|
| CC 线束 P0–P4 | [`cc-butler-gap-analysis-2026-05.md`](../active/cc-butler-gap-analysis-2026-05.md) | `tests/test_cc_p3_p4_features.py` 等 |
| 四报告 PR1–PR6 | [`four-reports-capabilities-2026-05.md`](../../guides/four-reports-capabilities-2026-05.md) | 路线图 §9 |
| 五报告 PR-F1–F6 | [`five-reports-capabilities-2026-05.md`](../../guides/five-reports-capabilities-2026-05.md) | 同上 |
| 五报告 P5–P10 | [`external-agent-reports-capabilities-2026-05.md`](../../guides/external-agent-reports-capabilities-2026-05.md) | `./scripts/butler-five-reports-gate.sh` |
| 外部 Agent PR-X1–X6 | [`external-agent-reports-improvement-roadmap-2026-05.md`](../roadmaps/external-agent-reports-improvement-roadmap-2026-05.md) §10 | `tests/test_external_agent_*.py` 等 |
| OpenCode / OpenClaw / OMO | 各 learning-plan | 各 `test_opencode_*` 等 |
| MCP 薄客户端 | [`butler-mcp-capability-2026-05.md`](../comparisons/butler-mcp-capability-2026-05.md) | `BUTLER_MCP_ENABLED` |
| **扩展选型规程** | [`active/extension-rd-loop-2026-06.md`](../active/extension-rd-loop-2026-06.md) | MCP 守门 · 选型一页纸 · EXT-4 gate |
| **EXT-4 GitHub OpenAPI** | [`ext-4-second-openapi-2026-06.md`](../active/extension-candidates/ext-4-second-openapi-2026-06.md) | `butler-extension-ext4-gate.sh` |

---

## 5. 路线图文档权属（维护 map）

| 文档 | 保留用途 | 与本文关系 |
|------|----------|------------|
| [`../DOCUMENTATION.md`](../../DOCUMENTATION.md) | **文档体系** L0–L5、维护规则、语料专项 | 本文的上位索引 |
| [`four-reports-out-of-scope-2026-05.md`](../decisions/four-reports-out-of-scope-2026-05.md) | **四报告 18 项否决** 权威正文 | 本文 §1.1 索引 |
| [`five-reports-not-done-2026-05.md`](../decisions/five-reports-not-done-2026-05.md) | **五报告** 变更记录 + P5–P10 表 | 本文 §1.2、§2.1 索引 |
| [`four-reports-improvement-roadmap-2026-05.md`](../roadmaps/four-reports-improvement-roadmap-2026-05.md) | 四报告 **已落地** PR 核对 §9 | 勿从 §3–§5 旧表找待办 |
| [`five-reports-improvement-roadmap-2026-05.md`](../roadmaps/five-reports-improvement-roadmap-2026-05.md) | 五报告 **已落地** PR-F §9 | 同上 |
| [`external-agent-reports-improvement-roadmap-2026-05.md`](../roadmaps/external-agent-reports-improvement-roadmap-2026-05.md) | 外部五报告 **已落地** §10 | 同上 |
| [`external-reference-deferred-2026-05.md`](../../guides/external-reference-deferred-2026-05.md) | Hermes/LC/Dify/LF defer 细节 | 本文 §1.3、§3 |
| [`post-consolidation-roadmap-2026-05.md`](../active/post-consolidation-roadmap-2026-05.md) | **产品运营** backlog | 本文 §3.4 |
| 本文 **§3.6** | **产品评估 P0/P1 立项**（2026-06） | 带验收标准与脚本链 |
| 各 `*-comparison-report-2026-05.md` | 历史对照全文 | **不**作为待办来源；以本文 + 速查为准 |

**维护规则**

1. 新增 **否决** → 写入 §1 对应表 + 更新 `four-reports-out-of-scope` 或 `five-reports-improvement-roadmap` §6。  
2. 新完成 **子集** → 从 §2 删除或改表述，写入 §4 速查。  
3. 新 **可选立项** → 写入 §3，附来源报告链接。  
4. 各路线图 §9/§10 核对表只维护 **✅ 已落地**，勿复活旧 P0/P2 行为待办。

---

## 6. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：合并四报告/五报告/外部 Agent/OpenCode/defer/post-consolidation 未做与边界 |
| 2026-05-25 | 链入 [`DOCUMENTATION.md`](../../DOCUMENTATION.md) 文档体系 |
| 2026-05-26 | 记录 SQLite observation store 首版落地后的残留风险与后续收口项 |
| 2026-06-26 | **§3.6** 产品评估立项表（PROD-P0-01…P2-04）：G1-04、配置剖面、pytest 叙事、Dev/Owner/记忆 P1、工程 P2 |
| 2026-06-26 | **§3.7** PROD-P3 done + owner-week1-ops-sim / owner-p3-wechat-sim 守门链 |
| 2026-06-25 | **EXT-5** MarkItDown MCP manifest + integrate/preflight/gate（Verify 真机待办） |
| 2026-06-22 | **PROD-P2-04** EXT-4 选型闭环 + 季度评审 |
