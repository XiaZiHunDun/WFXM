# EXT-3：文档 ingest（RAG 进料，非 RAG 平台）

> **状态**：**Decide ✅**（2026-06-19）· **Integrate ✅**（2026-06-20）· **Verify ✅**（2026-06-20）  
> **规程**：[`extension-rd-loop-2026-06.md`](../extension-rd-loop-2026-06.md)  
> **项目试点**：灵文1号 [`stack.yaml`](../../../../projects/LingWen1/stack.yaml) · `ingest_pilot_dirs`

---

## 1. 痛点与信号

| 项 | 内容 |
|----|------|
| **现象** | 已有 `semantic_index` + `butler memory search`；**缺** PDF/Office/批量目录进料；自建 MinerU/Docling 全家桶已否决 |
| **信号** | 灵文参考书、竞品 PDF、`docs/research/` 报告无法一键召回；Owner 重复「把这份资料放进记忆」 |
| **不做的信号** | 需要 RAGFlow Studio、知识图谱、多租户 ingest 队列 → 见 roadmap §1 否决 |

---

## 2. 候选对比

| 候选 | 类型 | 依赖 | 结论 |
|------|------|------|------|
| **A. MarkItDown MCP / CLI** | sidecar | `documents` extra 或 MCP | **推荐**（与 pyproject `markitdown` 对齐） |
| **B. Unstructured MCP** | MCP | Node/Python | 备选（更重） |
| **C. 外部 cron 写 chunk MD** | L2 脚本 | 无新 core | **fallback**；手工 `memory reindex` |
| **D. RAGFlow / Dify ingest** | 平台 | 重 | **否决** |

---

## 3. 推荐路径

- [x] **sidecar CLI ingest** → `.butler/ingest/*.md` + `ingest_pilot_dirs` Markdown 直索引
- [x] **optional-extra** `documents`（markitdown）供 CLI 预研
- [ ] 新 builtin 重管线
- [ ] 否决

**分工**：

```text
单文件 CLI 试转  →  markitdown（pip install -e ".[documents]"）
批量 / 微信触发  →  MCP ingest（opt-in）→ butler memory reindex
检索            →  现有 semantic_index（不改 core）
```

---

## 4. 验收标准

| 类 | 标准 |
|----|------|
| **功能** | 指定试点目录（见下）ingest 后，`butler memory search <关键词> --project 灵文1号` 可召回片段 |
| **试点目录** | `projects/LingWen1/novel-factory/references/` · `projects/LingWen1/docs/research/` |
| **安全** | ingest 只读源目录；无任意路径写；默认关 |
| **开关** | 新 env 须 opt-in（如 `BUTLER_INGEST_ENABLED=0` 默认）；无新 core 硬依赖 |
| **守门** | `test_ragflow_p0_retrieval.py` · `test_markdown_chunking.py`；ingest 后 reindex 脚本绿 |

---

## 5. 不做什么（边界）

- 不接 RAGFlow/Dify Graph / Langflow
- 不把 markitdown 拉进 `gateway` extra（Gateway 不必装 PDF 栈）
- 不让 ingest 自动 mutating 项目正文（`novel-factory/.../04_正文` 除外非本 EXT 范围）

---

## 6. 接入步骤（Integrate 阶段草案）

### 6.1 开发机预研（现即可做）

```bash
pip install -e ".[documents]"
# 单文件试转
python -c "from markitdown import MarkItDown; print(MarkItDown().convert('path/to/file.pdf').text_content[:500])"
```

### 6.2 批量试点（立项后）

1. 将参考书 PDF / 调研 MD 放入 `novel-factory/references/` 或 `docs/research/`
2. 运行 ingest sidecar（`bash scripts/butler-ingest-pilot.sh` 或 `butler memory ingest --project 灵文1号 --reindex`）
3. `bash scripts/butler-memory-reindex.sh --project 灵文1号`
4. `butler memory search "<关键词>" --scope project --project 灵文1号`

### 6.4 Verify 记录（2026-06-20）

| 项 | 结果 |
|----|------|
| 参考书 | `novel-factory/references/` 00–09 + mood-samples + research |
| 索引 | `ingest_pilot_dirs` Markdown → **41** 层级块（reindex 后） |
| 检索 | `--scope project` 抽测：暗皇/枢纽城/裂痕和解/炼狱 等命中 |
| PDF | `references/external/` 占位就绪；有文件时 `butler-ingest-pilot.sh` |
| 守门 | `test_document_ingest` · `test_markdown_chunking` · `test_ragflow_p0_retrieval` 绿 |
| 生产 | 灵文 `.env` `BUTLER_INGEST_ENABLED=1`；Gateway 已重启 |


- 删除 chunk 缓存 + reindex；或关闭 ingest env

---

## 7. Decide 记录（2026-06-19）

| 决策 | 内容 |
|------|------|
| 下一扩展 | **EXT-3** 优先于 EXT-2（无具体 REST API 需求前） |
| 试点项目 | 灵文1号 |
| 试点目录 | `novel-factory/references/` + `docs/research/` |
| 接入形态 | sidecar/MCP → 现有 index；**不**新 RAG 平台 |
| Gateway extra | 保持 `[gateway]`，**不含** `documents` |

---

## 8. Track

| 日期 | 事件 |
|------|------|
| 2026-06-20 | **Verify ✅**：参考书 00–09 + mood-samples；41 chunk 索引；守门 pytest 绿 |
| 2026-06-20 | Integrate ✅：`butler/memory/document_ingest.py` · `butler memory ingest` · `butler-ingest-pilot.sh` |
| 2026-06-19 | Decide ✅；`stack.yaml` + 试点 README |
