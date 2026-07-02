# 记忆统一检索 ADR（P3-H）

> **状态**：2026-06-30 · Phase 1–3 已落地（coding/transcript/observation/hybrid + 多 scope CLI + 诊断 telemetry）  
> **登记**：[`roadmap-backlog` §3.6](roadmap-backlog-and-boundaries-2026-05.md) · [`project-optimization-directions` §方向 H](../active/project-optimization-directions-2026-06.md)

## 背景

Butler 记忆分散在多条召回链：

| 层 | 存储 | 当前入口 |
|----|------|----------|
| Owner 画像 | `profile` | `butler_recall` scope=profile |
| 跨项目经验 | `experience` FTS/向量 | `butler_recall` scope=experience |
| 项目 MEMORY | `project_notes` / Pending | `butler_remember` + scope=project |
| 编码经验 L3/L4 | `coding_experiences.json` | DevLoop / B9 检索（**未**暴露给 recall 工具） |
| Transcript FTS | sqlite `transcript_fts` | `butler transcript search` / cron |
| Observation | `observations.db` | opt-in 派生 |

Owner/Agent 在对话中只能稳定调用 `butler_recall` 三 scope，与「六层记忆」文档不一致。

## 决策

1. **统一入口**：逐步扩展 `butler_recall` + `butler memory search` 的 `scope` 枚举，而非新建平行工具。
2. **分阶段**：先只读、关键词/既有索引；不合并写入路径。
3. **ChromaDB**：`butler/memory/vector_store.py` 保持 **实验/非生产**；生产语义走 `SemanticMemoryIndex`（`memory_vectors.db`）。已在 [`memory-ops.md`](../../guides/memory-ops.md) 说明。
4. **Observation Store**：Phase 3 再评估是否升为辅助检索层（需 opt-in 与权重 ADR）。

## Phase 1（✅ 2026-06-30）

- 新增 `butler_recall` **`scope=coding`**：搜索租户 L4 + 当前项目 L3 `coding_experiences.json`
- 实现：`butler/memory/coding_recall.py`
- CLI：`butler memory search --scope coding`
- 测试：`tests/test_coding_recall.py`

## Phase 2（✅ 2026-06-30）

- 新增 `butler_recall` **`scope=transcript`**：薄包装 `butler/core/transcript_search.py`
- 实现：`butler/memory/transcript_recall.py`
- CLI：`butler memory search --scope transcript`；`--scope all` 或逗号列表并行
- `/诊断 详细`：`rag_by_scope` 各 scope 一行最近召回 telemetry
- 测试：`tests/test_transcript_recall.py`

## Phase 3（✅ 2026-06-30）

- **`scope=observation`**（opt-in `BUTLER_MEMORY_OBSERVATION_RECALL=1`）：workspace `observations.db` 关键词检索
- **`scope=hybrid`**（opt-in `BUTLER_MEMORY_UNIFIED_RECALL=1`）：experience + project + coding 分数归一化合并；observation 路径命中时加权 boost
- 实现：`butler/memory/observation_recall.py`、`butler/memory/unified_recall.py`、`ObservationStore.search`
- 权重 env：`BUTLER_MEMORY_UNIFIED_WEIGHT_*`、`BUTLER_MEMORY_OBSERVATION_RECALL_BOOST`
- 测试：`tests/test_unified_recall.py`

## 非目标

- Honcho/mem0 插件（H-P2-3）
- 替换 DevLoop 内 `CodingKnowledgeContext.process_task`
- 写入 coding 经验进 `butler_remember`（仍走 DevEngine 管线）

## 验收（Phase 1–3）

```bash
PYTHONPATH=. pytest tests/test_coding_recall.py tests/test_transcript_recall.py tests/test_unified_recall.py -q
butler memory search "pytest verify" --scope coding --limit 5
butler memory search "keyword" --scope transcript
BUTLER_MEMORY_OBSERVATION_RECALL=1 butler memory search "jwt" --scope observation --project <name>
BUTLER_MEMORY_UNIFIED_RECALL=1 butler memory search "pytest" --scope hybrid --project <name>
butler memory search "keyword" --scope all --json
```
