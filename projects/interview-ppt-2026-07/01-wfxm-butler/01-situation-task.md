# 01 · WFXM Butler · S+T（背景与任务）

> **技术标签**：跨进程工具路由 + 多源记忆治理
> **项目定位**：自托管多项目 AI 管家（Self-hosted multi-project AI butler）
> **代码规模**：`butler/` 目录 1254 个 Py 文件（v4 自建 Loop）

---

## 0. 一句话定位（30 秒电梯稿）

WFXM Butler 是**自托管的多项目 AI 管家**：你在**微信**或 **CLI** 下指令，系统用自建的 **Agent Loop** 理解意图，通过 `delegate_task` 委派给 dev/content/review 等子代理在项目 workspace 里改代码或写内容；**分层记忆**跨会话延续上下文。

**典型主路径**：`/切换 项目` → `/简报` 看状态 → 「交给开发代理…」或 `/改` 结构化委派 → 验收卡确认结果。

---

## 1. 痛点真实性（Situation）

> 禁用"领导让我做"。这里只描述**业务/工程瓶颈**。

### 痛点 A：远程多项目管理的物理瓶颈

**场景**：作为开发者/作者，需要**用手机在地铁上**指挥多个仓库、小说、软件项目的进度。
- 微信是日常最高频入口，但**主流 AI 工具都是 Web/IDE-first**——手机上没法用
- 切项目要切多个 App（GitHub、IDE、Notion、飞书），上下文断裂

### 痛点 B：现成 AI Agent 工具的"五不贴"

试用过主流方案，逐一不贴：

| 候选方案 | 不贴的原因 |
|----------|------------|
| ChatGPT/Claude 单聊 | 无工具、无记忆、无项目隔离 |
| Cursor/Cline IDE Agent | 必须开电脑，远程不可用 |
| LangChain / AutoGen | 定位是"框架"而非"产品"，自托管 + 微信集成都要自己写 |
| Coze / Dify 低代码 | 多租户 SaaS、不可控、定制能力差 |
| Open Interpreter 本地 Agent | 跨工具协调弱，记忆缺 |

### 痛点 C：跨工具调度的工程难题

工具数量超过 10 个（GitHub / 文件系统 / 记忆 / Skill / 定时任务 / 向量库…）后，单 Agent 无法稳定调度：

- **工具幻觉**（hallucinated tool name/args）
- **上下文溢出**（>50K token 时 LLM 失准）
- **权限边界模糊**（dev 子代理能改什么不能改什么）
- **跨会话状态丢失**（明天重开会话又解释一遍）

---

## 2. Agent 必要性（Task）

### 为什么必须用 Agent，不能用传统脚本/SQL？

1. **意图模糊**："把昨天灵文1号的 ch01 改一下"——需要 NLU + 项目路由 + 委派判断
2. **工具组合复杂**：单次任务可能跨 5+ 个工具（memory recall → read file → patch → verify → ingest → 记忆）
3. **跨会话状态**：用户的"昨天那个 bug"需要历史检索 + 上下文关联
4. **权限分级**：Lead 模式（厂长）vs 子代理（dev/content/review）需要差异化工具集

### 为什么自建 Loop，不用 LangGraph / AutoGen？

**关键决策**：**自建 Agent Loop**（`butler/core/agent_loop.py`），拒绝 LangGraph 替换路线。

| 维度 | LangGraph / AutoGen | Butler 自建 Loop |
|------|---------------------|------------------|
| 部署形态 | 服务 / 容器 | 单文件 CLI + 微信网关 |
| 数据存储 | DB / 云 | 文件 SSOT（Markdown/JSONL）+ SQLite 索引 |
| 记忆 | 框架自带 | 三层（Owner / 项目 / 会话），Markdown 是 SSOT |
| 微信集成 | 无 | 原生 iLink + message_handler |
| 权限门控 | 需自实现 | 原生（permissions.yaml + `MAX_DELEGATE_DEPTH=2`） |
| 失败回退 | 需自实现 | 原生（`llm_fallback` + `reactive_compact`） |
| 调试可读性 | 框架封装深 | 每个工具调用、压缩、记忆写入都是 Python 函数，可断点 |

**核心选型理由**（一句话）：单租户自托管场景下，"框架自带能力"是**负债**而非**资产**——文件 SSOT 比数据库更易审计、SQLite 索引可 `reindex`、所有能力都在 1254 个 Py 文件内可控。

---

## 3. 你的 KPI（可量化）

| 指标 | 目标 | 测量方式 | 当前实际 |
|------|------|----------|----------|
| **微信 TTFT**（首包响应） | < 3s | `butler doctor` + `/诊断` | ⚠ 待你补充（项目内无埋点） |
| **工具调用成功率** | > 95% | runtime metrics | ⚠ 待你补充（无聚合统计） |
| **跨会话 Recall@3** | > 80% | `embedding_health.py` `check_embedding_recall(min_recall=0.8)` | ✅ **0.8 阈值**（smoke 5 GT / 8 seed） |
| **runtime jobs 完成率** | > 99% | weekly consistency report | ⚠ 待你补充（无聚合统计） |
| **Owner 验收通过率** | > 90% | 验收卡 confirm/abort 计数 | ⚠ 待你补充（建议演示前后各统计一周） |
| **测试覆盖** | > 80% | 分层 pytest gate | ✅ 当前 `tests/` ~80%（676+ tests passed，见 `323862e`） |

---

## 4. 你的角色（0-1 架构 + 主要开发者 + 决策者）

| 角色 | 我承担 | 说明 |
|------|--------|------|
| **0-1 架构** | ✅ 是 | 设计 v4 分层模型（核心 / 记忆 / 微信 / 工具 / 调度），主导关键模块选型 |
| **主要开发者** | ✅ 是 | `butler/` 1254 Py 文件，主导设计并实现 Agent Loop / Gateway / 记忆三层 / 委派门控 |
| **产品边界决策** | ✅ 是 | 决策"做什么"和"不做什么"（见下"不做"清单），提交 commit 即决策落地 |
| **测试与发版守门** | ✅ 是 | 编写分层 pytest gate、CC harness、五报告 gate |
| **Owner 视角 UX 决策** | ✅ 是 | 自己就是 Owner，所有 UX 决策从"我自己用得爽不爽"出发 |

### 我做的产品边界决策（"不做"清单）

> 这一项是面试官爱听的"判断力"——能主动拒绝比能做更重要。

- ❌ 不做全量 MCP Host / 市场（只做薄 MCP 客户端）
- ❌ 不做 IDE 子进程替代 Loop（远程微信场景不适配）
- ❌ 不做多租户 SaaS（单租户自托管定位）
- ❌ 不用 LangGraph 替换自建 Loop（见 §2）
- ❌ 不做浏览器自动化默认路径（安全边界）

---

## 5. 面试追问风险预案（高频问题）

| 高频问题 | 一句话回答 |
|----------|-----------|
| 为什么不用 Postgres？ | 单租户自托管；文件 SSOT 可读可审计；SQLite 只做派生索引，可 `reindex` |
| MCP Host vs 客户端？ | 我们只做薄 MCP 客户端；不做 npm 级 Host/市场 |
| CC 线束是什么？ | 对标 Claude Code CLI 的上下文经济、read-state、队列等回归测试（`./scripts/butler-cc-harness-gate.sh`） |
| `transcript.jsonl` vs `transcript_fts.db`？ | jsonl 是真相源；fts.db 是 FTS5 索引，可 rebuild |
| 为什么不直接用 Claude Code？ | 微信入口 + 多项目切换 + 分层记忆是 Claude Code 没有的能力；CLI 是我们的 Dev 子代理能力上限对标 |

---

## 6. ⚠ 待你补充 / 校对

写完后请确认：

- [ ] §3 KPI 实际数字（特别是 TTFT / Recall@3 / jobs 完成率）
- [ ] §2 "自研 vs LangChain"对比表是否合适？如不合适可删除整段
- [ ] §4 角色定位是否准确？（如"主要开发者"应改为"主导 + 多人协作"）
- [ ] §0 是否需要在 PPT 第一页就出现"30 秒电梯稿"全文？

---

## 附录：本文件对应 PPT 页面建议

| PPT 页 | 对应章节 |
|--------|----------|
| P1 封面 | §0 一句话定位 + 技术标签 |
| P2 痛点 | §1 三个痛点（远程 / 五不贴 / 跨工具工程难题） |
| P3 为什么必须 Agent | §2 第一段（4 个理由） |
| P4 自研 vs 框架对比 | §2 第二段（表格） |
| P5 我的角色 | §4 角色表 + 不做清单 |