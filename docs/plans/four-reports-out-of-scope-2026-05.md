# 四份对标报告 — 明确不做清单（Out of Scope）

> **状态**：长期有效（2026-05-25 起）  
> **用途**：Agent / 开发者在提需求或写规划时，先查本文，避免把已否决的能力当作「待实现」。  
> **关联**：[四报告合并路线图](four-reports-improvement-roadmap-2026-05.md) §7、[落地核对表](four-reports-improvement-roadmap-2026-05.md) §9

---

## 1. 产品边界（一句话）

Butler v4 是 **微信管家 + 多项目自建 Agent Loop**，不是浏览器自动化平台、不是 RAG 平台、不是训练栈、不是 IDE 插件。  
四份报告的价值是 **抽子集增强上下文、检索、收尾与实验协议**，而不是再叠一套大系统。

---

## 2. 明确不做总表

| # | 能力 / 方向 | 来源报告 | 不做原因 | Butler 已用替代 |
|---|-------------|----------|----------|-----------------|
| 1 | 内嵌 **browser-use 式 CDP / DOM / 截图** 流水线 | browser-use | 依赖重、运维与安全面大；与微信网关场景无关 | `web_fetch`（可选）；`terminal`；不入 Loop 内嵌浏览器 |
| 2 | **每步截图 + 视觉模型** 驱动 Loop | browser-use | 成本、延迟、隐私；无法在微信展示 | 文本工具 + 可选 `web_fetch` |
| 3 | 部署或嵌入 **RAGFlow 全栈**（ES/Infinity/MinIO/Studio） | RAGFlow | 与「零新增重依赖」冲突；产品非知识库平台 | 自建 `semantic_index` + `chunking` + hybrid FTS |
| 4 | RAGFlow **Web Studio / 多租户 Dataset** | RAGFlow | SaaS 形态超出边界 | CLI `butler memory search` + `/诊断` |
| 5 | **MinerU / Docling** 全家桶 ingest | RAGFlow | 重依赖、另立项 | Markdown 切块 + 项目 `reindex` |
| 6 | 把 **`reference/awesome-design-md/`** 73 套标本打入主仓库 | awesome-design-md | 体积、品牌、与 `reference/` gitignore 策略 | 项目内 `DESIGN.md` + `design_preset` + 模板 |
| 7 | **getdesign.md / Stitch** 商业生成流水线 | awesome-design-md | 与 Butler 产品无关 | 人工维护 `DESIGN.md` + `design-system` skill |
| 8 | 依赖本地 **`preview.html`** 色板预览 | awesome-design-md | reference 无此文件；微信无法展示 | `read_file DESIGN.md` + token 核对 |
| 9 | 独立 **「设计 Agent 运行时」**（替代 Loop） | awesome-design-md | 违背 v4 单 Loop | profile + skill + `design_md_sections` + `ui-build` |
| 10 | **Playwright 视觉回归** / 浏览器农场 | awesome-design-md、AGENTS | 已界定不做 E2E 浏览器农场 | `ui-dev-qa-loop` 文本验收 + read_file |
| 11 | **`npx @google/design.md lint`** 默认进微信 Loop | awesome-design-md | 可选 CI 工具，非运行时依赖 | 文档约定 + review 步骤核对 |
| 12 | 默认微信路径 **通宵自治**（NEVER STOP） | autoresearch、browser-use | 需人在回路；安全与可控 | `goal_loop` 默认关；cron/CLI 可选 |
| 13 | 实验 **每轮自动 git commit** 上 main | autoresearch | 污染主分支 | 实验分支 + CLI `experiment discard --apply-reset`（须显式开关） |
| 14 | 指标未改善时 **自动 `git reset`**（无门控） | autoresearch | 误伤风险 | `BUTLER_EXPERIMENT_GIT_RESET=0` 默认；仅 CLI 显式 |
| 15 | **LLM 辅助子 query 分解**（额外模型调用） | RAGFlow | 成本与延迟；启发式已够用 | `BUTLER_RAG_SUBQUERY` 规则拆分 + 合并 |
| 16 | 让 Butler 变成 **训练平台**（autoresearch 训练细节） | autoresearch | 非产品目标 | `software-research` harness + 账本 |
| 17 | 让 Butler 变成 **浏览器控制平台** | browser-use | 同上 #1 | — |
| 18 | **LangSmith / 全链路 tracing SaaS** 默认接入 | 多份外部对标 | 已有 `runtime_metrics` + `/诊断` | 进程内 metrics，零外部 APM 依赖 |

---

## 3. 按报告展开的「不做」原文索引

便于回溯细节，仍以**本文 §2 总表**为裁决依据。

### 3.1 RAGFlow（[`ragflow-butler-comparison-report-2026-05.md`](ragflow-butler-comparison-report-2026-05.md)）

- 不部署 RAGFlow 子服务；不默认引入 ES/Infinity/MinIO。
- 不做 Web 知识库 Studio、多租户 Dataset、Confluence/S3 全量同步（除非另立项）。
- RF-P2 级「项目目录 watch + MinerU/Docling 全家桶」— **不做**。

### 3.2 browser-use（[`browser-use-butler-comparison-report-2026-05.md`](browser-use-butler-comparison-report-2026-05.md)）

- **明确不做**：在 `butler/core` 内嵌 CDP、每步截图、browser-use Cloud Skills（除非产品改边界）。

### 3.3 awesome-design-md（[`awesome-design-md-butler-comparison-report-2026-05.md`](awesome-design-md-butler-comparison-report-2026-05.md)）

- **P3 明确不做**：73 套内置、Stitch 商业流水线、Playwright 视觉农场、替代 Loop 的设计 Agent 运行时。

### 3.4 autoresearch（[`autoresearch-butler-comparison-report-2026-05.md`](autoresearch-butler-comparison-report-2026-05.md)）

- **明确不做**：默认路径通宵自治、无门控每轮提交、训练实现细节迁移。
- `goal_loop` 与 **experiment 标量驱动** 分离，不合并。

---

## 4. 与「已落地」的边界（避免误解）

以下能力**已实现**，不属于 §2「不做」：

| 能力 | 模块 / 开关 |
|------|-------------|
| 检索 fallback + 诊断 + CLI verbose | `semantic_index`、`rag_diagnostics`、`butler memory search` |
| 启发式子 query | `query_decompose`、`BUTLER_RAG_SUBQUERY` |
| Loop 减熵（nudge / 预算 / inject_once / stale read） | `tool_guardrails`、`loop_budget_nudge`、`tool_result_storage` |
| DESIGN 上下文 | `design_md_sections`、`ui-build`、`design_preset` |
| 实验 harness + 账本 + METRIC | `experiments/`、`BUTLER_EXPERIMENT_MODE`、`.butler/experiments.tsv` |
| 支撑线 E 子集 | `tool_modes`、隐式参数、schema 预优化、token 粗算 |

完整核对见 [路线图 §9](four-reports-improvement-roadmap-2026-05.md#9-落地核对表2026-05)。

---

## 5. 何时可以重新讨论

仅当 **产品边界书面变更**（例如明确要做「浏览器管家」或「知识库 SaaS」）时，方可把 §2 某项移出本文并单独立项。  
否则 Agent 应默认：**不在此清单内的增量，走现有 Loop/Gateway/工具扩展即可。**

---

## 6. 维护义务

- 四报告路线图若新增「不做」项，须同步更新 **§2 总表**。
- 若实现某条原「不做」能力，从表中删除并注明替代方案废弃日期。

---

## 7. 五报告增量「不做」（索引）

claude-mem / cc-switch / PEG / TradingAgents / LobeHub 特有否决项（S1–S11）见 [`five-reports-improvement-roadmap-2026-05.md`](five-reports-improvement-roadmap-2026-05.md) §6。  
**本文 §2 总表优先**；五报告仅补充未在四报告中单列的边界。
