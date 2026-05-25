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
| **F** | 内联工具压缩实验 | `BUTLER_INLINE_TOOL_COMPRESS`；长会话评估用，未实现开关 |
| **G** | MCP/Skill **SSOT + `butler mcp sync`** | 跨项目 MCP/Skill 单一索引与同步 CLI；当前仅薄 MCP |
| **G** | Thinking/协议整形 | 按模型自动注入 thinking 头；`model_capabilities` 仅静态表，未接 transport |
| **G** | `butler://` provider 预设库 | cc-switch 对照中的预设分发，未做 |
| **H** | Prompt 迭代 **eval 闭环** | 语料 case + rubric 自动化（非 APE 搜 prompt） |
| **H** | 辅助模型 **injection 评分** | 入站消息 LLM 打分 + human_gate；当前仅规则 `injection_guard` |
| **H** | `BUTLER_REFLEXION_WRITE_EXPERIENCE` | Reflexion 写入长期 experience；当前仅 ephemeral banner |
| **I** | 完整 **Pydantic 终局校验** | 已有 JSON fence + `output_schema` 解析；无 schema 校验/重试管线 |
| **I** | 固定 **Bull/Bear 多角色图** | TradingAgents 演示图；非默认微信路径 |
| **J** | **ToolsEngine**（manifest 合并、FC 检查） | MCP 深化时再做 |
| **J** | 市场 manifest **安装前扫描**深化 | 与 REG-P4 / lobehub 源联动，未做 |
| **J** | post_session **persona/preference/experience 自动分层写入** | `session_summary.json` 有壳；字段多为空，未接 LLM 抽取 |

---

## 3. 已做子集、可深化（非「未作」，勿误判为缺失）

| 项 | 当前状态 | 深化方向 |
|----|----------|----------|
| 观察者队列 | 默认 `BUTLER_MEMORY_OBSERVER_QUEUE=0` | 开 env 即用；非 Chroma Worker |
| Reflexion | 默认 `BUTLER_REFLEXION_EPHEMERAL=0` | 开 env 即用 |
| `model_capabilities` | `butler/transport/model_capabilities.py` 静态表 | 接到 `anthropic_transport` 等 |
| 终局 schema | `parse_structured_output` + workflow `output_schema` | 加 Pydantic + 失败重试 |
| MCP | `BUTLER_MCP_ENABLED` + `.butler/mcp.yaml` | 不等于 S11 全量 Host |

---

## 4. 与四报告「不做」的关系

| 文档 | 范围 |
|------|------|
| [four-reports-out-of-scope §2](four-reports-out-of-scope-2026-05.md) | RAGFlow 全栈、CDP/截图、73 套 DESIGN、通宵自治等 **18 项** |
| 本文 §1 | 五报告 **特有** S1–S11 |
| 本文 §2 | 五报告路线图 **P2 未排期** |

四报告与五报告 **均已收口 P0/P1 主路径**；新增能力若命中 §1 或四报告 §2，应直接拒绝或改产品边界。

---

## 5. 维护义务

- 新否决项：写入 §1 并同步 [路线图 §6](five-reports-improvement-roadmap-2026-05.md)。
- 新完成 P2：从 §2 删除，在路线图 §9 标 ✅。
- 若实现原否决能力：从 §1 删除并注明日期与替代方案废弃说明。

---

## 6. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：S1–S11、P2 未排期、可深化对照、四报告交叉引用 |
