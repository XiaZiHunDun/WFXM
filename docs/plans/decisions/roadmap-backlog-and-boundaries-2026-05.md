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
| **真要排期新功能** | 本文 **§3** |
| **查已落地能力** | 本文 **§4** |
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

### 2.4 依赖分层 / 本地状态（外部依赖策略）

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
- **2026-Q3 首批试点**：EXT-1 网页采集 MCP（[一页纸](extension-candidates/ext-1-web-scrape-mcp-2026-06.md)）· EXT-2 OpenAPI/HTTP · EXT-3 文档 ingest（见规程 §5）  
- **Agent 可** 起草选型一页纸；**不可** 无人值守改 core 依赖或绕过白名单

### 3.1 安全 / 凭证 / 网关

| 项 | 来源 | 说明 |
|----|------|------|
| `secrets.yaml` **Fernet 加密** | Dify 对标 | 明文+600 为过渡；`cryptography` 可选 |
| `execute_code` 生产开放 | Hermes | 默认 `BUTLER_EXECUTE_CODE=0`；须安全评审 |
| 微信真·流式**编辑**回复 | Hermes | 依赖 iLink 能力；现有 progressive 为补充消息 |
| 权限 **LLM 分类器** | Hermes | 与「无 classifier」原则冲突 |

### 3.2 检索 / 工具 / 协议

| 项 | 来源 | 说明 |
|----|------|------|
| 全量 RAG **ingest 管线** | Dify | 已有 search；ingest 另立项 — **规程** [`extension-rd-loop` §5 EXT-3](../active/extension-rd-loop-2026-06.md) |
| OpenAPI 声明式 HTTP 工具 | Dify | `.butler/tools/*.yaml` 需产品定义 — **规程** [`extension-rd-loop` §5 EXT-2](../active/extension-rd-loop-2026-06.md) |
| LLM 工具模拟器 | LangChain | 仅测试路径，ROI 低 |
| LangChain **Checkpointer** 断点续跑 | LangChain | 单进程微信非刚需 |
| **corpus live 全量**（非 smoke） | PEG | 成本高；已有 `--corpus-live-full` 上限子集 |

### 3.2.1 Observation Store 残留项（开发完成后统一收口）

| 项 | 来源 | 说明 |
|----|------|------|
| `observations.tsv` -> `observations.db` 一次性迁移 | SQLite observation store 首版 | 兼容早期试用数据；可在首次发现 DB 缺失且 TSV 存在时导入 |
| observation 路径历史排序/权重优化 | SQLite observation store 收口 | 当前以最近命中为主；后续可按工具类型、成功率、访问频次细化排序 |
| observation 导出/诊断命令 | SQLite observation store 收口 | 目前主要经 `PreRead` 与 `read_file` 隐式消费；如需人工排障可另加只读诊断命令 |

### 3.3 OpenCode 净新增（P2/P3）

见 [`opencode-butler-comparison-report-2026-05.md`](../comparisons/opencode-butler-comparison-report-2026-05.md)「仍明确暂缓」与 P2/P3 表：Compaction 一等任务、异步委派通知、worktree 会话、LSP、Share 公网 URL、Post-edit format 等。

### 3.4 产品运营（post-consolidation）

见 [`post-consolidation-roadmap-2026-05.md`](../active/post-consolidation-roadmap-2026-05.md) 轨道 A–D **未完成项**（灵文运营、Git 项目注册、识图 P3、主机工具白名单等）。与对标路线图 **正交**。

### 3.5 仓库 / 双实例（整理备忘）

见 [`p3-deferred-deep-dive-2026-05.md`](../archive/p3-deferred-deep-dive-2026-05.md)（双实例、记忆排查 — **非**五报告 P3）。

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
| **扩展选型规程** | [`active/extension-rd-loop-2026-06.md`](../active/extension-rd-loop-2026-06.md) | MCP 守门 · 选型一页纸 |

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
