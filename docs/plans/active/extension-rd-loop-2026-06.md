# 扩展选型与接入规程（Extension R&D Loop）

> **版本**：1.0 | 2026-06-18  
> **性质**：L2 决策规程 — **不改** Loop/Gateway/记忆公理；规定「何时、如何引入开源/外部能力」  
> **决策 SSOT**：[`roadmap-backlog-and-boundaries-2026-05.md`](../decisions/roadmap-backlog-and-boundaries-2026-05.md) §0–§1  
> **执行面 SSOT**：[`execution-surface-design.md`](../../architecture/execution-surface-design.md) · [`extension-registry-paths.md`](../../architecture/extension-registry-paths.md)

---

## 1. 原则（造车蓝图）

| 必须自建（车架） | 优先外购/开源（零件） |
|------------------|------------------------|
| 微信 Gateway、入站队列、出站策略 | 嵌入模型（fastembed 等 optional） |
| `agent_loop`、上下文经济学、委派门控 | MCP Server（GitHub、Firecrawl、DB…） |
| 记忆契约（Profile / Experience / Facts） | 重 PDF/网页解析（MCP 或 sidecar，不进 core） |
| 权限格、`project.yaml` 工具白名单 | 观测后端（LangFuse opt-in） |

**不做**：用 LangGraph/Dify/LobeHub **替换** Loop；全量 MCP Host；为接插件而把能力默认写进 `dependencies`。

**接入优先级**（同能力多路径时）：

```text
MCP（薄 Client，默认关）
  → pyproject optional-dependencies
    → 小型 builtin（仅当 MCP 无法覆盖且微信主路径强依赖）
      → 否决（§1 命中则停止）
```

---

## 2. 六步闭环（每季度 ≥1 项或按需）

| 步 | 名称 | 输入 | 产出 | 负责人 |
|----|------|------|------|--------|
| **O** | Observe 观测 | `/诊断`、`butler doctor`、eval/B9 弱项、Owner 需求、对照报告 | 1 段「缺口陈述」+ 可量化信号 | Agent 草拟 + Owner 确认痛点 |
| **R** | Research 选型 | 缺口 + `docs/plans/comparisons/*` + 社区 MCP 目录 | **选型一页纸**（见 §4 模板） | Agent |
| **D** | Decide 决策 | 一页纸 | Backlog 行或 **否决记录**；须过 §0 决策流 | Owner |
| **I** | Integrate 接入 | 批准 | `mcp.yaml` / optional-extra / 文档；**opt-in** env | 开发 + 发版 |
| **V** | Verify 验证 | 接入 PR | 守门脚本 + 可选 corpus live；`/诊断` 新行 | CI + 真机抽测 |
| **T** | Track/Retire 跟踪 | 生产 2–4 周 | 保留 / 升级 / 下线；经验写入 tenant Experience | Owner + eval |

**自动化边界**：

- ✅ Agent 可：读对照报告、起草选型一页纸、更新 `comparisons/` 附录、跑 eval 对比  
- ❌ Agent 不可：无人值守 `pip install` 进生产、改 core 默认依赖、绕过 `project.yaml` / `permissions.yaml`

---

## 3. 接入路径速查

| 路径 | 何时用 | 配置面 | 守门 |
|------|--------|--------|------|
| **MCP** | 长尾工具、SaaS、浏览器、GitHub | `~/.butler/mcp.yaml`、`.butler/mcp.yaml`；`BUTLER_MCP_ENABLED=1` | [`butler-mcp-capability`](../comparisons/butler-mcp-capability-2026-05.md) · `butler mcp scan` |
| **optional-extra** | 单一 Python 库、无 MCP 官方 Server | `pyproject.toml` `[project.optional-dependencies]` | `dependency-policy` · 默认安装不含 |
| **workflow / delegate** | 多步编排、子进程隔离 | `butler/workflows/` · `delegate_task` | `test_p2_workflow_permissions` |
| **Skill** | 流程参考，非高信任执行 | tenant/project `skills/` | 语料 / 不替代 builtin |

路径合并：[`extension-registry-paths.md`](../../architecture/extension-registry-paths.md)。

---

## 4. 选型一页纸模板

立项或季度评审时复制本节为 `docs/plans/active/extension-candidates/<id>-YYYY-MM.md`（可选，单页即可）。

```markdown
# EXT-xxx：<能力名>

## 痛点与信号
- 现象：…
- 信号：`/诊断` / eval / B9 / Owner 原话

## 候选（2–3）
| 候选 | 类型 | 许可 | 依赖重量 | 微信场景 fit |
|------|------|------|----------|--------------|
| A | MCP / lib / SaaS | … | 低/中/高 | … |

## 推荐路径
- [ ] MCP  [ ] optional  [ ] builtin  [ ] 否决

## 验收标准
- 功能：…
- 安全：permissions / owner gate / SSRF
- 开关：`BUTLER_*` 或 `mcp_*` 白名单
- 守门：`pytest …` / `butler-pre-release-smoke.sh` 子集

## 不做什么（边界）
- …

## 回滚
- 关 env / 移 mcp.yaml 条目 / `butler mcp reload`
```

---

## 5. 优先队列（2026-Q3 首批）

以下三项来自 [`roadmap-backlog` §3.2](../decisions/roadmap-backlog-and-boundaries-2026-05.md) 与对照报告 **已验证缺口**，适合作为 Extension R&D Loop 试点。**未承诺排期**；每项须单独走 §2 D→I。

### EXT-1 — 网页采集增强（MCP 优先） → [`extension-candidates/ext-1-web-scrape-mcp-2026-06.md`](extension-candidates/ext-1-web-scrape-mcp-2026-06.md)

| 维度 | 内容 |
|------|------|
| **状态** | Decide ✅ · Integrate ✅ · **Verify ✅**（2026-06-18 微信真机） |
| **痛点** | 内置 `web_fetch` 适合轻量 HTTP→文本；复杂站点（JS 渲染、反爬、批量 crawl）自建成本高、调试久 |
| **信号** | 查资料类任务失败率；对照 [`firecrawl-butler-comparison`](../comparisons/firecrawl-butler-comparison-2026-05.md)、[`browser-use-butler-comparison`](../comparisons/browser-use-butler-comparison-report-2026-05.md) Phase D |
| **候选** | **Firecrawl MCP**（scrape/crawl API）；自建薄 `web_fetch` 仅保留 fallback；Browser MCP（真交互，权限 `ask`） |
| **推荐** | MCP 外挂 + 保留 builtin 薄层；**不**引入 Playwright 集群进 core |
| **验收** | `BUTLER_MCP_ENABLED=1` + project 白名单 `mcp_firecrawl_*`；`bash scripts/butler-extension-ext1-preflight.sh`；`/诊断` MCP 段 |
| **守门** | `test_mcp_features.py` · 可选 live（API key） |

### EXT-2 — 声明式 HTTP / OpenAPI 工具（MCP 或 YAML）

| 维度 | 内容 |
|------|------|
| **痛点** | 每个 SaaS（日历、工单、内部 REST）写 builtin 周期长；Dify 类「OpenAPI → tool」成熟 |
| **信号** | Backlog §3.2 OpenAPI；Owner 重复「接某某 API」需求 |
| **候选** | **openapi-mcp** 类 Server；Butler 侧 `.butler/tools/*.yaml` 声明（Backlog，需产品 schema）；社区 REST MCP |
| **推荐** | 先 **MCP 生态已有 Server**；YAML 声明仅当 MCP 覆盖不足且需微信无 Node 依赖时立项 |
| **验收** | 1 个试点 API（如 readonly GET）；`permissions.yaml` last-match；secrets 仅 `secrets.yaml` |
| **守门** | SSRF 测试 · `test_security_audit` 相关 |

### EXT-3 — 文档 ingest（RAG 进料，非 RAG 平台）

| 维度 | 内容 |
|------|------|
| **痛点** | 已有 `semantic_index` + search；**缺** PDF/Office/批量目录 ingest；自建 MinerU/Docling 全家桶已否决 |
| **信号** | Backlog §3.2 全量 RAG ingest；四报告 RF-P2 **不做** 重管线 |
| **候选** | Unstructured / MarkItDown **MCP**；一次性 CLI + `memory reindex`；外部 cron 写 chunk 文件再 index |
| **推荐** | **sidecar/MCP ingest** → 写入现有 index 路径；**不**接 RAGFlow/Dify Graph |
| **验收** | 指定 `docs/` 或 PDF 目录 ingest → `butler memory search` 可召回；默认关；无新 core 重依赖 |
| **守门** | `test_ragflow_p0_retrieval.py` · `test_markdown_chunking.py` |

---

## 6. 与现有运维节奏对齐

| 节奏 | 动作 |
|------|------|
| **发版前** | 若 EXT 项已接入：`butler-pre-release-smoke.sh` + MCP 子集 |
| **每周** | B9 / eval-sync 弱项 → 是否触发 O 步 |
| **每季度** | 评审 §5 队列；更新一页纸；关闭或移入 [`roadmap-backlog` §3](../decisions/roadmap-backlog-and-boundaries-2026-05.md) |
| **G1-04 窗后** | OT2 硬反馈是否指向某 EXT（如 delegate 救援 vs 新 MCP） |

---

## 7. Agent 工作说明

1. 新会话读本文 + `roadmap-backlog` §0，**勿**从 comparison 正文 P 表直接立项。  
2. 起草选型时引用 **已有** 对照报告章节，避免重复调研。  
3. 接入 PR 须含：env 表、`mcp.yaml.example` 片段（若 MCP）、`CONTRIBUTING` 守门命令。  
4. 全文对照报告只增 **落地状态** 与 **EXT-id 交叉引用**，不复活旧 P0 表。

---

## 8. 相关文档

| 文档 | 关系 |
|------|------|
| [`execution-surface-design.md`](../../architecture/execution-surface-design.md) | Builtin / Skill / MCP 信任级联 |
| [`butler-mcp-capability-2026-05.md`](../comparisons/butler-mcp-capability-2026-05.md) | MCP 薄客户端 |
| [`dependency-policy-2026-05.md`](../../guides/dependency-policy-2026-05.md) | optional-dependencies |
| [`skill-mcp-registry-2026-05.md`](../comparisons/skill-mcp-registry-2026-05.md) | Skill Hub / MCP catalog 方向 |
