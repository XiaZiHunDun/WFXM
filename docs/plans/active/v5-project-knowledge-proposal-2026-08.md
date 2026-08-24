# Butler v5 Project Knowledge — 立项草案（2026-08-23）

> **状态**：**Accepted**（2026-08-24 Owner 决策）  
> **前置**：P3 MCP 四 server + Grant 验收已闭环（[`v5-mcp-multi-server-handoff-2026-08.md`](v5-mcp-multi-server-handoff-2026-08.md)）  
> **目标架构 SSOT**：[`butler-v5/DESIGN.md`](../../../butler-v5/DESIGN.md) §9  
> **生产事实**：[`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md) §6.0b–c  
> **产品边界**：[`v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md)

---

## 1. 为什么要立项

当前 v5 已交付 **Transcript**（Message）、**Durable Memory MVP**、**Document ingest MVP**，但缺少按 **projectId** 组织的「项目级资料检索」能力。

典型 Owner 场景（微信 / CLI）：

| 场景 | 现有能力缺口 |
| --- | --- |
| 「WFXM 里我们关于 MCP 的决策是什么？」 | `recall_durable_memory` 按 **subject**，不按 project；Document 无 project 维度 |
| 「灵文1号 novel-factory 的设定在哪？」 | 只能靠 `read_file` 扫 workspace；无项目语料索引 |
| 「这个项目的 DESIGN.md / MEMORY 摘要？」 | v4 有 `search_project_knowledge`；**v5 未移植** |
| 计划模式 / 委派前先查项目资料 | 无统一 `recall_project_*` 工具 |

**立项触发条件**（DESIGN §15）：真实召回需求出现，且 Transcript + Durable Memory + Document 子串召回不够 — **已满足**（多项目微信管家 + WFXM/LingWen 等并行）。

---

## 2. 三层记忆边界（必须遵守）

```text
Transcript (Message)     — 对话原文；已有
Durable Memory           — Owner 个人偏好/事实；subject 维度；已有 MVP
Project Knowledge        — 项目文档/结构化资料；projectId 维度；本立项
Run 压缩/滚动摘要        — 执行产物；永不自动升级为任一层
```

不变量（DESIGN §17.9）：

- Project Knowledge **不等于** Durable Memory（不存「Owner 喜欢深色模式」类个人事实，除非明确标注为项目决策）
- 向量索引仅为**可重建检索实现**，不是事实源
- 默认 **结构化 + 全文/子串**；embedding 需单独触发证据

---

## 3. v5 可复用基础（不重复造轮）

| 已有 | 复用方式 |
| --- | --- |
| `conversations.project_id`（migration `0007`） | Run / 微信 inbound 已带 projectId |
| `documents` + `recall_document` | 可扩展 `project_id` 列或 provenance.projectId |
| `durable_memories` + `recall_durable_memory` | 项目级「决策事实」可选挂 projectId（与 subject 并存） |
| Owner API / CLI 模式 | `butler document` / `butler memory` 已验证 |
| Policy → Grant → MCP markitdown | 文档入站后可 ingest + 索引 |
| `GET /v1/owner/conversations?projectId=` | 项目会话列表已有 |

**不要**从 v4 `butler/memory/` 或 `search_project_knowledge` **直接移植**；只借鉴产品语义，在 v5 schema + Run Engine 上重写。

---

## 4. v4 参考（产品语义，非实现依据）

v4 `search_project_knowledge` 行为摘要：

- 作用域：**当前 project workspace**
- 数据源：项目 `MEMORY.md`、facts、语义索引（`butler_recall` project scope）
- 输出：结构化 JSON（chunk_id、source_path、score）
- 可选：`BUTLER_CORPUS_ROUTING=1` 多 scope 路由

v5 MVP **不必**首日恢复向量/混合检索；先用 **显式 ingest + 子串/路径召回** 对齐 Document MVP 哲学。

---

## 5. 建议 MVP 范围（P5-K1）

### 5.1 数据

- 新表 `project_knowledge_items`（或扩展 `documents` 加 `project_id` — **推荐独立表**，避免 document 全局 subject 语义混淆）  
  最小字段：

  ```text
  id, project_id, title, kind, source_path?, extracted_text,
  provenance (json), byte_size, created_at, updated_at
  ```

- `kind` 枚举首版：`file_snapshot` | `memory_md` | `manual_note` | `ingested_document`（引用 documents.id）

- **不**默认全盘索引 workspace；仅 Owner/Agent **显式 ingest** 或 **watch 清单内路径**（见 §5.4 可选）

### 5.2 写入路径

| 路径 | 说明 |
| --- | --- |
| Owner CLI/API | `butler project-knowledge add/list/get/delete --project WFXM` |
| 从 Document promote | `POST .../documents/:id/promote-project-knowledge?projectId=` |
| 从 workspace 快照 | `add --project WFXM --file path/to/DESIGN.md`（read_file 同源路径校验） |
| Agent 工具（高风险） | `ingest_project_file` → Policy Ask |

### 5.3 召回

- 新工具 **`recall_project_knowledge`**（低风险 read，默认可自动执行）
  - 参数：`projectId`（默认当前 conversation projectId）、`query`（子串）、`limit`
  - 返回：title、kind、source_path 片段、匹配行 — **不**编造未命中内容
- 工作集注入：opt-in `BUTLER_V5_PROJECT_KNOWLEDGE=1`（对齐 Durable Memory 注入模式）

### 5.4 明确 MVP 不做

- RAG Studio / 自动全盘索引 / 默认 embedding
- Dream 巩固、ContextGraph
- 跨 project 联合检索（首版单 projectId）
- 第二套 Run Engine 或绕过 Policy 的 ingest
- 把 Run 压缩摘要写入 Project Knowledge

### 5.5 可选 P5-K1.1（立项时可裁剪）

- 配置文件 `config/project-knowledge-sources.json`：按 projectId 列出允许 ingest 的路径 glob（类似 MCP manifest）
- markitdown MCP 抓 PDF/Office 后直接 chain 到 project ingest（需 Grant）

---

## 6. 安全与 Policy

| 动作 | 风险 | 默认 Policy |
| --- | --- | --- |
| `recall_project_knowledge` | read | Allow（projectId 必须匹配当前 Run 上下文或 Owner 指定） |
| ingest / add / delete | write | Ask 或 Owner API only |
| 跨 project 读取 | read | **Deny**（硬边界） |
| 路径 ingest | read + workspace | 沿用 `read_file` 路径规则（无 `..`、workspace 内） |

ScopedGrant：首版 **不需要** 新 Grant 类型；写操作走现有 approval 或 Owner loopback API。

---

## 7. 验收标准（MVP Done ✅ 2026-08-24）

1. [x] **Schema**：migration 注册 + `pnpm test` 契约测试  
2. [x] **Owner API/CLI**：add/list/get/delete 对 `projectId=WFXM` 可 CRUD  
3. [x] **Loop 工具**：微信 inbound → `recall_project_knowledge` 命中已 ingest 条目  
4. [x] **边界**：Durable Memory / Document / Project Knowledge 三层不串；document delete 级联 PK  
5. [x] **文档**：`v5-production-architecture-2026-08.md` + `.env.example`  
6. [x] **回归**：不破坏 `recall_durable_memory` / `recall_document` / MCP 22 tools

---

## 8. 实施顺序（工程估算）

| 阶段 | 交付 | 估时 |
| --- | --- | --- |
| **K1-a** | domain 类型 + migration + persistence store | 0.5–1d |
| **K1-b** | Owner routes + CLI | 0.5d |
| **K1-c** | `recall_project_knowledge` 工具 + projectId 上下文 | 0.5d |
| **K1-d** | 测试 + production architecture 文档 | 0.5d |
| **K1.1** | sources.json watch / markitdown chain | ✅ 2026-08-24 |

**不**与 Project Knowledge 同批：Web UI、浏览器、向量索引、v4 机械迁移。

---

## 9. Owner 决策清单（已确认 2026-08-24）

- [x] **A. 场景确认**：首版 **WFXM + wechat 多项目** 足够；灵文1号非 Day-1 必做
- [x] **B. MVP 范围**：同意 §5.1–5.3（子串召回、显式 ingest、无 embedding）
- [x] **C. 数据源**：Owner 手动 + **workspace 文件快照** + **Document promote**
- [x] **D. 工具名**：保留 `recall_project_knowledge`
- [x] **E. 注入**：`BUTLER_V5_PROJECT_KNOWLEDGE=0`（opt-in，默认关）
- [x] **F. 优先级**：**下一优先**（P3 MCP 已闭环后实施 K1）

Owner 原文：

```text
Project Knowledge 立项：
- A: WFXM + wechat 足够
- B: 同意 MVP
- C: 手动 + workspace 快照 + Document promote
- D: 保留 recall_project_knowledge
- E: opt-in 默认 0
- F: 下一优先
```

---

## 10. 建议 Owner 回复模板

```text
Project Knowledge 立项：
- A: WFXM + wechat 足够 / 需灵文1号 Day-1
- B: 同意 MVP / 要加 embedding
- C: 手动 + workspace 快照 / 不要 Agent ingest
- D: 保留 recall_project_knowledge
- E: opt-in 0 默认
- F: 下一优先 / 延后
```

---

## 11. 相关链接

- 黑板：`.blackboard/state.md`（P3 MCP 已闭环，下一项 Project Knowledge）
- 路线图：[`v5-post-boundary-roadmap-2026-08.md`](v5-post-boundary-roadmap-2026-08.md) §P4 Durable Memory（Project Knowledge 未含）
- v4 知识图谱（历史参考）：[`project-knowledge-graph-2026-06.md`](../../guides/project-knowledge-graph-2026-06.md)

---

**草案一句话**：在 v5 已有 projectId + Document/Durable Memory 基础上，新增 **project 维度显式 ingest + 子串召回**，恢复「这个项目里我们决定过什么」能力，不引入 RAG Studio 或第二套引擎。
