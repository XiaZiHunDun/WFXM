# 规划文档索引

> 更新：2026-05-25 | 区分 **CC 线束**、**仓库整理**、**外部对标** 三套「P0/P2/P3」命名，勿混用。

## 命名对照（易混淆）

| 说法 | 文档 | 含义 |
|------|------|------|
| **CC 线束 P0–P4** | [`cc-butler-gap-analysis-2026-05.md`](cc-butler-gap-analysis-2026-05.md) | Claude Code 源码对照；Loop/Gateway 能力（压缩、队列、P3/P4 §11） |
| **仓库整理 P0–P2** | [`consolidation-2026-05.md`](consolidation-2026-05.md) | 目录瘦身、文档归档、死代码清理前置 |
| **仓库整理 P3** | [`consolidation-p3-implementation-2026-05.md`](consolidation-p3-implementation-2026-05.md) | 实现层熵减（与 CC P3 无关） |
| **外部对标 P0–P2** | [`reference-learning-plan-2026-05.md`](reference-learning-plan-2026-05.md) | Prometheus/OpenClaw/Dify **设计借鉴**（已收口，零依赖） |
| **外部对标阶段 A/B/C** | [`../guides/external-reference-roadmap-2026-05.md`](../guides/external-reference-roadmap-2026-05.md) | Hermes/LangChain/Dify/Langflow **已落地**（2026-05-25） |
| **Prompt Corpus 线 D/E** | [`prompts-corpus-butler-comparison-2026-05.md`](prompts-corpus-butler-comparison-2026-05.md) | system-prompts 语料库：工具 DSL、规划模式、transcript、大文件读、task_milestone |
| **OpenCode 对标 P0–P1** | [`opencode-learning-plan-2026-05.md`](opencode-learning-plan-2026-05.md) | 压缩/prune/权限/doom loop/委派/指令 walk-up（**已落地**） |
| **OpenCode 对照报告** | [`opencode-butler-comparison-report-2026-05.md`](opencode-butler-comparison-report-2026-05.md) | 全量设计对照 + P1–P3 净新增建议（2026-05-25） |
| **Langflow 对照报告** | [`langflow-butler-comparison-2026-05.md`](langflow-butler-comparison-2026-05.md) | Butler ↔ Langflow 全量对照 + P0–P2 提炼建议（2026-05-25） |
| **LangChain 对照报告** | [`langchain-butler-comparison-2026-05.md`](langchain-butler-comparison-2026-05.md) | Butler ↔ LangChain v1 Agent/中间件 全量对照 + P0–P2 提炼建议（2026-05-25） |
| **Dify 对照报告** | [`dify-butler-comparison-2026-05.md`](dify-butler-comparison-2026-05.md) | Butler ↔ Dify 全量对照 + P0–P2 提炼建议（零依赖，2026-05-25） |
| **Firecrawl 对照报告** | [`firecrawl-butler-comparison-2026-05.md`](firecrawl-butler-comparison-2026-05.md) | Butler ↔ Firecrawl 全量对照 + P0–P2 提炼建议（零依赖，2026-05-25） |
| **MCP 薄客户端 P3** | [`butler-mcp-capability-2026-05.md`](butler-mcp-capability-2026-05.md) | stdio/HTTP Client + `butler mcp serve`（**已落地**） |
| **OpenClaw 对标 OC-P0–P2** | [`openclaw-learning-plan-2026-05.md`](openclaw-learning-plan-2026-05.md) | 前置压缩、工具环、reply 准入、doctor、terminal 绑定、delegate_yield（**已落地**） |
| **OMO 对标 OMO-P0–P2** | [`omo-learning-plan-2026-05.md`](omo-learning-plan-2026-05.md) | tool-pair、压缩检查点、待办续跑、委派类别、魔法词、hashline、规则引擎（**已落地**） |
| **Skill/MCP Registry** | [`skill-mcp-registry-2026-05.md`](skill-mcp-registry-2026-05.md) | 搜索 / 安装 / 装配（**已落地 REG-P0 / MCP-P0**） |
| **四报告 Sprint A–D** | [`../guides/sprint-roadmap-2026-05.md`](../guides/sprint-roadmap-2026-05.md) | Firecrawl / agency / Gemini / awesome **已落地子集**（2026-05-25） |
| **Codex Sprint C0–C2** | [C0](../guides/sprint-codex-c0-2026-05.md) · [C1](../guides/sprint-codex-c1-2026-05.md) · [C2](../guides/sprint-codex-c2-2026-05.md) | Codex 对标 **C0–C2 已落地** |
| **Codex 对照报告** | [`codex-butler-comparison-2026-05.md`](codex-butler-comparison-2026-05.md) | Codex CLI 全量对照 + 验收索引 |
| **agency-agents 提炼** | [`agency-agents-extraction-analysis-2026-05.md`](agency-agents-extraction-analysis-2026-05.md) | NEXUS / Handoff / dev-qa-loop → **Sprint B 已落地子集** |
| **Gemini CLI 对照报告** | [`gemini-cli-butler-comparison-report-2026-05.md`](gemini-cli-butler-comparison-report-2026-05.md) | G-P0 masking/压缩 → **Sprint A**；G-P1+ 仍 defer |
| **awesome-llm-apps 对照报告** | [`awesome-llm-apps-butler-comparison-report-2026-05.md`](awesome-llm-apps-butler-comparison-report-2026-05.md) | MCP profiles / corrective recall → **Sprint B–C 已落地子集** |
| **awesome-design-md 对照报告** | [`awesome-design-md-butler-comparison-report-2026-05.md`](awesome-design-md-butler-comparison-report-2026-05.md) | DESIGN.md 标本库 → **DESIGN 上下文管线（待落地）**；≠ awesome-llm-apps |
| **autoresearch 对照报告** | [`autoresearch-butler-comparison-report-2026-05.md`](autoresearch-butler-comparison-report-2026-05.md) | 自主实验组织：harness/账本/keep-discard；零依赖，阶段 A–C |
| **browser-use 对照报告** | [`browser-use-butler-comparison-report-2026-05.md`](browser-use-butler-comparison-report-2026-05.md) | Butler ↔ browser-use 全量对照 + P0–P2 提炼建议（零 CDP 依赖，2026-05-25） |
| **RAGFlow 对照报告** | [`ragflow-butler-comparison-report-2026-05.md`](ragflow-butler-comparison-report-2026-05.md) | Butler ↔ RAGFlow 全量对照 + RF-P0–P2 提炼建议（零依赖，分析完成未落地，2026-05-25） |

## 当前状态（2026-05-25）

| 类别 | 状态 |
|------|------|
| CC 线束 §4–§11 | 已落地 main（见 gap 文档 §3 核验） |
| 仓库整理 | P0–P3 已完成 |
| 外部对标（Prometheus/OpenClaw/Dify 线） | P0–P2 已落地；**无后续必做项** |
| 外部对标（Hermes/LangChain/Dify/Langflow 阶段 A/B/C） | **已落地**；defer 见 [`../guides/external-reference-deferred-2026-05.md`](../guides/external-reference-deferred-2026-05.md) |
| Prompt Corpus 阶段 D/E | **已落地**；验收 [`../guides/phase-d-prompt-corpus.md`](../guides/phase-d-prompt-corpus.md) |
| 四报告 Sprint A–D | **已落地**；验收 [`../guides/sprint-roadmap-2026-05.md`](../guides/sprint-roadmap-2026-05.md) |
| Codex Sprint C0–C2 | **已落地**；`pytest tests/test_sprint_codex_c0.py tests/test_sprint_codex_c1.py tests/test_sprint_codex_c2.py` |
| OpenCode 对标 | P0–P2 已落地（SQLite 全量模型仍暂缓） |
| MCP P3 | 薄 Client + 诊断 + `butler mcp serve`（默认关闭） |
| OpenClaw OC-P0–P2 | 前置压缩 / AGENTS 节回灌 / 工具环 / Gateway 准入 / `butler doctor`（**已落地**） |
| OpenClaw OC-P3 子集 | transcript 索引 / 出站延迟 / 记忆离线 cron / hook fail-closed（**已落地**） |
| OMO OMO-P0–P2 | tool-pair 修复 / 压缩检查点 / 待办续跑 / 委派类别 / 魔法词 / hashline / goal_loop（**已落地**） |
| 产品后续 | [`post-consolidation-roadmap-2026-05.md`](post-consolidation-roadmap-2026-05.md) |

## 活跃参考

| 文档 | 用途 |
|------|------|
| [`cc-butler-gap-analysis-2026-05.md`](cc-butler-gap-analysis-2026-05.md) | 改 Loop/Gateway 前先看对照与落地状态 |
| [`post-consolidation-roadmap-2026-05.md`](post-consolidation-roadmap-2026-05.md) | 灵文运营、多项目、语料 |
| [`reference-learning-plan-2026-05.md`](reference-learning-plan-2026-05.md) | 外部项目学习记录（**已关闭**） |
| [`opencode-learning-plan-2026-05.md`](opencode-learning-plan-2026-05.md) | OpenCode 对标（**已落地 P0–P1**） |
| [`opencode-butler-comparison-report-2026-05.md`](opencode-butler-comparison-report-2026-05.md) | OpenCode ↔ Butler 全量对照报告 + 后续 P1–P3 |
| [`langflow-butler-comparison-2026-05.md`](langflow-butler-comparison-2026-05.md) | Langflow ↔ Butler 全量对照报告 + P0–P2 提炼建议 |
| [`langchain-butler-comparison-2026-05.md`](langchain-butler-comparison-2026-05.md) | LangChain ↔ Butler 全量对照报告 + P0–P2 提炼建议（零依赖） |
| [`dify-butler-comparison-2026-05.md`](dify-butler-comparison-2026-05.md) | Dify ↔ Butler 全量对照报告 + P0–P2 提炼建议（零依赖） |
| [`firecrawl-butler-comparison-2026-05.md`](firecrawl-butler-comparison-2026-05.md) | Firecrawl ↔ Butler 全量对照报告 + P0–P2 提炼建议（零依赖） |
| [`butler-mcp-capability-2026-05.md`](butler-mcp-capability-2026-05.md) | MCP 薄客户端（**已落地**） |
| [`openclaw-learning-plan-2026-05.md`](openclaw-learning-plan-2026-05.md) | OpenClaw 对标（**已落地 OC-P0–P2**） |
| [`omo-learning-plan-2026-05.md`](omo-learning-plan-2026-05.md) | Oh-My-OpenAgent 对标（**已落地 OMO-P0–P2**） |
| [`../guides/external-reference-roadmap-2026-05.md`](../guides/external-reference-roadmap-2026-05.md) | 四报告统一阶段 A/B/C + 验收 |
| [`../architecture/hermes-butler-comparison-2026-05.md`](../architecture/hermes-butler-comparison-2026-05.md) | Hermes 对照全文 |
| [`agency-agents-extraction-analysis-2026-05.md`](agency-agents-extraction-analysis-2026-05.md) | agency-agents（NEXUS）；Sprint B 子集已落地 |
| [`gemini-cli-butler-comparison-report-2026-05.md`](gemini-cli-butler-comparison-report-2026-05.md) | Gemini CLI；G-P0 → Sprint A，G-P1+ defer |
| [`awesome-llm-apps-butler-comparison-report-2026-05.md`](awesome-llm-apps-butler-comparison-report-2026-05.md) | awesome-llm-apps；Sprint B–C 子集已落地 |
| [`awesome-design-md-butler-comparison-report-2026-05.md`](awesome-design-md-butler-comparison-report-2026-05.md) | awesome-design-md；DESIGN.md / UI 上下文（待落地） |
| [`autoresearch-butler-comparison-report-2026-05.md`](autoresearch-butler-comparison-report-2026-05.md) | autoresearch（`reference/autoresearch`）；实验 harness 与账本提炼 |
| [`../guides/sprint-roadmap-2026-05.md`](../guides/sprint-roadmap-2026-05.md) | Sprint A–D 验收与内置工作流索引 |
| [`ragflow-butler-comparison-report-2026-05.md`](ragflow-butler-comparison-report-2026-05.md) | RAGFlow ↔ Butler；RF-P0–P2 路线图（**分析完成，待落地**） |
| [`codex-butler-comparison-2026-05.md`](codex-butler-comparison-2026-05.md) | Codex ↔ Butler；C0–C2 **已落地** |

## 归档 / 专项（按需打开）

| 文档 | 说明 |
|------|------|
| [`consolidation-2026-05.md`](consolidation-2026-05.md) | 整理方案全文 |
| [`memory-unification-implementation-2026-05.md`](memory-unification-implementation-2026-05.md) | 记忆双轨合并 |
| [`wechat-steer-implementation-2026-05.md`](wechat-steer-implementation-2026-05.md) | `/steer` 实现 |
| [`corpus-testing-module-design-2026-05.md`](corpus-testing-module-design-2026-05.md) | 语料测试模块 |
| [`p3-deferred-deep-dive-2026-05.md`](p3-deferred-deep-dive-2026-05.md) | 双实例 / 记忆排查备忘 |

`reference/` 目录（gitignore）由主公维护，**不在此索引内**。
