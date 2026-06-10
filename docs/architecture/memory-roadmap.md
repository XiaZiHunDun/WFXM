# 记忆模块路线图（含向量语义）

> 版本：2026-05-22 | 个人管家 · 单租户 · 微信主场景  
> 当前实现：`butler/memory/` + `session_lifecycle` + `post_session`（FTS5 + 可选本地向量 hybrid）  
> **检索信任策略（当前）**：经验 + 契约记忆 **优先**；Skill 为**未验证兜底**（[`§检索信任级联`](#检索信任级联)）。  
> ~~沉积层 v2 合一草案~~：[`v4-skill-memory-theory.md`](v4-skill-memory-theory.md) **已搁置**。

---

## 检索信任级联（Experience-first · Skill-fallback）

> 2026-06-09 确认 | **不改** [`v4-memory-theory.md`](v4-memory-theory.md) MA/MT 公理

| 层 | 信任 | 检索顺序 | 产品承诺 |
|----|------|----------|----------|
| 契约（Profile / MEMORY / facts） | 高 | 与经验一并优先（prefetch） | 管家负责 |
| 经验 \(\mathcal{K}_E\) | 高 | **第一优先** | 管家负责 |
| Skill（生态目录） | 低 | **兜底** 或经验 `skill:<名>` 点名 | **不负责**正确性 |

**注入策略**（`BUTLER_SKILL_INJECTION_MODE`，默认 `fallback`）：

1. `prefetch_turn_memory` 先注入经验/契约（`<memory-context>` 围栏）。  
2. `inject_skill_context` 查 `peek_experience_hits`：  
   - 命中 ≥ `BUTLER_SKILL_FALLBACK_MIN_EXPERIENCE_HITS` → **跳过** Router 全文（除非经验含 `skill:<名>`）。  
   - 无命中 → SkillRouter top-k（未验证参考）。  
3. system 中 skill 摘要带「未验证目录」免责声明。

**经验指针约定**（`tags` 或正文）：

| 指针 | 检索层 | 执行层 |
|------|--------|--------|
| `skill:<kebab-name>` | 仅注入该 Skill 正文 | 读取 frontmatter `preferred_tools` 并 pin（无需正文） |
| `tool:<builtin_name>` | — | pin 到 `tool_selector` |
| `mcp:<registered>` 或 `mcp:<server>/<tool>` | — | deferred 模式下 `promote_tools`（下轮可用完整 schema） |

**实现**：`butler/skills/injection_policy.py`、`experience_pointers.py`、`skill_tool_bridge.py`、`orchestrator.inject_skill_context`。

---

## 执行信任级联（Experience-first · Tool/MCP pins）

> 2026-06-09 | **不改** MA/MT | 与检索级联同构

| 执行面 | 默认 | 有经验命中 |
|--------|------|------------|
| Builtin Tool | 高信任，selector 正常裁剪 | 经验 `tool:` + `skill:` 的 `preferred_tools` **额外 pin** |
| MCP（deferred） | 仅 catalog + 显式 `load_mcp_tools` | 经验 `mcp:` **仅 promote 点名**；无指针则不自动 promote |
| Skill `preferred_tools` | 依赖 Skill 正文注入 | 经验 `skill:` 时**只读 frontmatter**，正文可跳过 |

**入口**：`agent_loop_phases._phase_enrich_user_text` → `collect_pinned_tools`。

---

## 1. Hermes 里「记忆」实际分两层

对照 `reference/hermes-agent`（本地只读标本）：

| 层级 | Hermes 做法 | 是否向量语义 |
|------|-------------|--------------|
| **内置** | `MEMORY.md` + `USER.md`，有界文本，会话初注入快照；`memory` 工具 add/replace/remove | **否**（与 Butler `profile.json` 同类） |
| **外部 Memory Provider** | `MemoryManager` 统一：`prefetch` 每轮召回、`sync` 每轮写入、`session end` 提炼；可选 Honcho / Mem0 / Supermemory 等 | **是**（各插件 embedding + 混合检索） |

Butler 已对齐 **内置层 + prefetch/sync/post_session**；**P0/P1 向量层**已本地化（`memory_vectors.db`，默认 hashing，无云存储）。

---

## 2. Butler 现状 vs 设计文档

| 能力 | 当前 v4（2026-05-22） | 历史设计稿（[`design-evolution-v0.5-v1.0.md`](../history/design-evolution-v0.5-v1.0.md) §11/§13） |
|------|----------------------|----------------------------------------|
| Owner 画像 | `profile.json` | ProfileStore ✅ |
| 跨项目经验 | `experience.db` + **FTS5**；可选向量 hybrid | ExperienceStore ✅ |
| 项目 MEMORY | `MEMORY.md` + Pending + 微信/CLI 待审命令 | MarkdownMemory ✅ |
| 项目语义索引 | `memory_vectors.db`；`butler_remember` / 批准 / reindex 同步 | SemanticMemoryIndex ✅ |
| 每轮召回 | experience hybrid + **项目 MEMORY query 向量预取** + 围栏注入 | get_relevant_context ✅ 部分 |
| 向量 / 混合检索 | `BUTLER_SEMANTIC_MEMORY=1` 启用；`=0` 仅 FTS | BM25+向量 hybrid ✅ P1 已落地 |
| queue_prefetch | `BUTLER_QUEUE_PREFETCH=1` 上轮结束后后台 warm 缓存 | Hermes 可选 ✅ P2 |
| 机读 facts | `facts.json` SSOT + `knowledge.db` 同步镜像；预取 + `butler_recall` scope=project | ✅ |

---

## 3. 目标架构（Butler 版）

```mermaid
flowchart TB
  subgraph human [人类可读 SSOT]
    MD[MEMORY.md + profile.json]
  end
  subgraph index [机读检索层]
    FTS[experience.db FTS5]
    VEC[(memory_vectors.db)]
  end
  subgraph turn [每轮]
    Q[用户 query] --> HY[hybrid + 项目向量]
    HY --> INJ["memory-context 围栏注入"]
  end
  subgraph write [写入]
    REM[butler_remember] --> MD
    REM --> VEC
    PS[post_session] --> MD
    PS --> VEC
  end
```

原则：

- **Markdown/JSON 仍为 SSOT**（微信可读、`/记忆待审` 不变）。
- **向量索引是衍生层**；失败降级 FTS。
- **conversation 永不进向量**。

---

## 4. 分阶段待办

### P0 — 方案与接口 ✅ 2026-05-21

- [x] `semantic_index.py`、`embedding.py`（local + openai/minimax 回退）
- [x] 文档与 `memory-guide.md`

### P1 — 最小可用 ✅ 2026-05-22

- [x] hashing hybrid、`prefetch` / `butler_recall`
- [x] `butler_remember` / Pending 批准 → 向量
- [x] `memory-reindex`、`/诊断` 无会话分层
- [x] CLI `/new` 双次 post_session 修复

### P2 — 对齐 Hermes 体验（本轮）

- [x] **项目 MEMORY query 对齐预取**（`search_project_memory_vectors` + `BUTLER_PREFETCH_PROJECT_HITS`）
- [x] **记忆围栏**（`<memory-context>` + 中文说明，防误读为用户指令）
- [x] **queue_prefetch**（`BUTLER_QUEUE_PREFETCH=1`，上轮结束后后台 warm，同 query 命中缓存）
- [x] **CLI `/记忆待审` / `/批准记忆`**（复用 gateway `memory_commands`）
- [x] **`facts.json` / auto_extract** 切换项目 + reindex 刷新；预取 + recall scope=project
- [x] 召回质量 fixture 测试（`tests/fixtures/memory_recall/cases.json`）
- [x] 三元组仅展示（`/记忆图谱`）

### P3 — 不做或暂缓

- 不接 Honcho/Mem0 等为默认
- 不做全书正文向量
- [x] Owner 画像向量索引（`owner_profile` source + 预取向量命中）
- [x] 三元组仅展示（`/记忆图谱`，不参与检索）
- [x] Ebbinghaus 衰减 + 访问计数加权（`BUTLER_MEMORY_HALF_LIFE_DAYS` / `BUTLER_MEMORY_ACCESS_BOOST`）

---

## 5. 环境变量

| 变量 | 用途 |
|------|------|
| `BUTLER_SEMANTIC_MEMORY` | `1` 启用向量；`0` 仅 FTS |
| `BUTLER_EMBEDDING_PROVIDER` | `local` / `openai` / `minimax` |
| `BUTLER_EMBEDDING_MODEL` | 模型 id |
| `BUTLER_VECTOR_HYBRID_WEIGHT` | hybrid 向量权重 |
| `BUTLER_PREFETCH_PROJECT_HITS` | 项目 MEMORY 向量预取条数（默认 5） |
| `BUTLER_QUEUE_PREFETCH` | `1` 启用上轮结束后后台 warm |
| `BUTLER_PREFETCH_CACHE_TTL` | warm 缓存秒数（默认 90） |
| `BUTLER_PREFETCH_FACTS_MAX_CHARS` | facts 预取块上限（默认 400） |
| `BUTLER_MEMORY_HALF_LIFE_DAYS` | 检索时间衰减半衰期（默认 30 天） |
| `BUTLER_MEMORY_ACCESS_BOOST` | 访问次数排序加权（默认 0.12） |

按角色收紧预取（代码内置，无需 env）：`lead` 偏 Architecture/Decisions/Notes；`content` 偏 Notes/Patterns；`dev` 含 API。query 命中后按 section 过滤；fallback 块长度 lead 800 / content 900 / dev 1200 字符。

---

## 6. 合并待改进清单

| 优先级 | 项 | 状态 |
|--------|-----|------|
| P0→P1 | 向量语义记忆本地化 | ✅ |
| P1 | `/诊断` 无会话静态分层 | ✅ |
| P1 | CLI `/new` 双次提炼 | ✅ |
| P2 | 项目 MEMORY query 预取 | ✅ |
| P2 | 记忆围栏 | ✅ |
| P2 | queue_prefetch | ✅（需 env 开启） |
| P2 | CLI 记忆待审 | ✅ |
| P2 | facts.json 预取 + recall | ✅ |
| P2 | 召回 fixture 测试 | ✅ |
| P2 | Pending 拒绝 + 向量清理 | ✅ |
| P2 | MEMORY remove/replace 向量同步 | ✅ |
| P2 | 项目预取关键词 fallback | ✅ |
| P2 | /诊断 预取缓存命中 | ✅ |
| P2 | post_session → 项目 MEMORY 向量同步 | ✅ |
| P3 | 外部云记忆默认接入 | 不做 |

---

## 7. 验收标准（P1，已满足）

1. paraphrase 可经 `butler_recall` 或 prefetch 命中已写入经验/项目记忆。
2. `BUTLER_SEMANTIC_MEMORY=0` 无回归。
3. `/诊断` 可见向量统计；`MEMORY.md` 仍为审批入口。

**灵文1号试点微信验收（2026-05-21）**：M1 `/诊断`（4 MEMORY / 4 向量）、M2 paraphrase → 2026-05-22 **通过**。记录见 `projects/LingWen1/docs/pilot-log.md`、`memory-guide.md`。

---

## 8. 参考文件

见历史版本 §7；Hermes `memory_manager.py`、`plugins/memory/supermemory` 仍作只读对照。
