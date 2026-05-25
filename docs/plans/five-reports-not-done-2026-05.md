# 五报告路线图 — 未作清单（2026-05）

> **状态**：长期有效；PR-F1–F6 **已落地**后，本文记录**仍未实现**或**明确不做**的项。  
> **已落地速查**：[`../guides/five-reports-capabilities-2026-05.md`](../guides/five-reports-capabilities-2026-05.md)  
> **路线图核对表**：[`five-reports-improvement-roadmap-2026-05.md`](five-reports-improvement-roadmap-2026-05.md) §9  
> **四报告否决（18 项）**：[`four-reports-out-of-scope-2026-05.md`](four-reports-out-of-scope-2026-05.md) §2（优先于本文）

提新需求前：先查四报告 §2，再查本文 **§1 否决**；若属 **§2 未排期 P2**，需单独立项，勿与 PR-F1–F6 重复验收。

---

## 1. 否决型「不做」（产品边界，勿立项）

来源：五报告路线图 §6（S1–S11）。除非产品边界变更，**不实现**。

| # | 能力 | 来源 | 原因 | Butler 替代 |
|---|------|------|------|-------------|
| S1 | claude-mem **Bun Worker + Chroma MCP** | claude-mem | 运行时/依赖栈不符 | `semantic_index` + `.butler/observations.tsv` |
| S2 | claude-mem **IDE 插件 / Viewer UI** | claude-mem | 入口是微信 | CLI / 微信命令 |
| S3 | CC Switch **Tauri 桌面 + 托盘** | cc-switch | 非服务端产品 | CLI + 微信 `/诊断` |
| S4 | CC Switch **五 CLI live 配置双向同步** | cc-switch | 维护面过大 | `project.yaml` + 原子写 |
| S5 | CC Switch **内置 HTTP 代理全家桶** | cc-switch | 网络中间层越界 | 薄 MCP + 现有 transport |
| S6 | PEG **LangChain Agent / notebook 运行时** | PEG | 教学标本 | 自建 `agent_loop` + prompt |
| S7 | PEG **ToT / APE 全自动 prompt 搜索** | PEG | 成本不可控 | 语料测试 + 人工改 prompt |
| S8 | TradingAgents **LangGraph + 行情 API** | tradingagents | 领域/依赖越界 | `task_orchestrator` + workflow YAML |
| S9 | TradingAgents **SQLite checkpoint 进 core** | tradingagents | 与 transcript 策略冲突 | `session_transcript` + 人工门控 |
| S10 | LobeHub **浏览器 Agent Loop / Chat UI** | lobehub | 产品形态不同 | 微信 Gateway + Butler Loop |
| S11 | LobeHub **全量 MCP Host + OTEL 默认** | lobehub | 重依赖 APM | `BUTLER_MCP_ENABLED` 薄客户端 + `runtime_metrics` |

---

## 2. 路线图 P2 / 未排期（未做，可另开 PR）

五报告 §3 中 **P2** 或 §9 标 **—** 的项；PR-F1–F6 **未包含**。

| 主线 | 项 | 说明 |
|------|-----|------|
| **G** | Thinking/协议整形（深化） | `BUTLER_THINKING_PROTOCOL=1` 已接 system hint；无 API beta 头全自动矩阵 |
| **G** | `butler://` provider 预设库 | cc-switch 对照中的预设分发，未做 |
| **H** | Prompt 迭代 **eval 闭环** | 语料 case + rubric 自动化（非 APE 搜 prompt） |
| **H** | 辅助模型 **injection 评分（LLM）** | 已有规则分 `BUTLER_INJECTION_SCORE` + transcript；无 LLM 打分 + human_gate 联动 |
| **I** | 完整 **Pydantic 终局校验（深化）** | PR-X5 已落地 `validate_structured_output` + `maybe_repair_structured_output`；无全量 Pydantic 模型树 |
| **I** | 固定 **Bull/Bear 多角色图** | TradingAgents 演示图；非默认微信路径 |
| **J** | **ToolsEngine**（manifest 合并深化） | FC 检查子集已落地 `BUTLER_TOOLS_ENGINE`；无市场 manifest 合并 |
| **J** | 市场 manifest **安装前扫描**深化 | 与 REG-P4 / lobehub 源联动，未做 |
| **J** | post_session **persona/preference/experience 自动分层写入** | `session_summary.json` 有壳；字段多为空，未接 LLM 抽取 |

---

## 3. 已做子集、可深化（非「未作」，勿误判为缺失）

| 项 | 当前状态 | 深化方向 |
|----|----------|----------|
| 观察者队列 | 默认 `BUTLER_MEMORY_OBSERVER_QUEUE=0` | 开 env 即用；非 Chroma Worker |
| Reflexion | 默认 `BUTLER_REFLEXION_EPHEMERAL=0` | 开 env 即用 |
| `model_capabilities` | `butler/transport/model_capabilities.py` 静态表 | 接到 `anthropic_transport` 等 |
| 终局 schema | `output_schema` 校验 + 一次 LLM repair（`BUTLER_OUTPUT_SCHEMA_*`） | 全量 Pydantic 类型树 + 多轮 repair |
| MCP | `butler mcp sync` + `mcp-ssot.yaml`；deferred 发现 | 不等于 S11 全量 Host |
| Skills SSOT | `butler skills sync` + `skills-ssot.yaml` | lockfile 快照，非 Hub 自动升级 |
| Reflexion 写入 | `BUTLER_REFLEXION_WRITE_EXPERIENCE=0` | `.butler/experiences/reflexion.jsonl` |

---

## 4. 与外部 Agent 五报告路线图的关系

[`external-agent-reports-improvement-roadmap-2026-05.md`](external-agent-reports-improvement-roadmap-2026-05.md) 中 **PR-X4/X5** 与本文 §2 部分重叠（MCP deferred、Pydantic 终局、MCP SSOT）。**否决项**仍以本文 §1 与四报告 §2 为准；**可立项**项以该路线图 §4 PR 为准。

---

## 5. 与四报告「不做」的关系

| 文档 | 范围 |
|------|------|
| [four-reports-out-of-scope §2](four-reports-out-of-scope-2026-05.md) | RAGFlow 全栈、CDP/截图、73 套 DESIGN、通宵自治等 **18 项** |
| 本文 §1 | 五报告 **特有** S1–S11 |
| 本文 §2 | 五报告路线图 **P2 未排期** |

四报告与五报告 **均已收口 P0/P1 主路径**；新增能力若命中 §1 或四报告 §2，应直接拒绝或改产品边界。

---

## 6. 维护义务

- 新否决项：写入 §1 并同步 [路线图 §6](five-reports-improvement-roadmap-2026-05.md)。
- 新完成 P2：从 §2 删除，在路线图 §9 标 ✅。
- 若实现原否决能力：从 §1 删除并注明日期与替代方案废弃说明。

---

## 7. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：S1–S11、P2 未排期、可深化对照、四报告交叉引用 |
| 2026-05-25 | §4：交叉引用 external-agent-reports 路线图 |
| 2026-05-25 | §2/§3：Pydantic 子集、MCP deferred 已与 PR-X4/X5 对齐 |
| 2026-05-25 | P5：`mcp/skills sync`、ToolsEngine FC、reflexion write、injection 启发式分 |
| 2026-05-25 | P5：`mcp/skills sync`、inline compress、reflexion write、injection 规则分、ToolsEngine FC |
