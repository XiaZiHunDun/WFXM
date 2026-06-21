# 参考书 / 设定素材（EXT-3 ingest 试点）

> **用途**：放置 PDF、Markdown、竞品摘录等**只读参考**，供 `butler memory search` / `search_project_knowledge` 召回。  
> **规程**：[`ext-3-document-ingest-2026-06.md`](../../../../docs/plans/active/extension-candidates/ext-3-document-ingest-2026-06.md)

## 目录结构（2026-06-20 已初始化）

| 文件 | 说明 |
|------|------|
| [00-index.md](./00-index.md) | **入口索引** |
| [01-world-and-power-system.md](./01-world-and-power-system.md) | 世界观、境界、势力 |
| [02-character-bible.md](./02-character-bible.md) | 人物弧线、形态日志 |
| [03-plot-timeline-foreshadowing.md](./03-plot-timeline-foreshadowing.md) | 三卷、时间轴、伏笔 |
| [04-writing-craft-checklist.md](./04-writing-craft-checklist.md) | 文风与审查清单 |
| [05-consistency-rules.md](./05-consistency-rules.md) | 一致性硬规则 |
| [06-locations-atlas-vol1.md](./06-locations-atlas-vol1.md) | 卷1 地点志 |
| [07-items-artifacts.md](./07-items-artifacts.md) | 道具与信物 |
| [08-locations-atlas-vol2-vol3.md](./08-locations-atlas-vol2-vol3.md) | 卷2–3 地点志 |
| [09-character-relationships-timeline.md](./09-character-relationships-timeline.md) | 人物关系时间线 |
| [mood-samples/vol1-tone-anchors.md](./mood-samples/vol1-tone-anchors.md) | 卷1 情绪语气锚点 |
| [mood-samples/vol2-tone-anchors.md](./mood-samples/vol2-tone-anchors.md) | 卷2 裂痕/和解锚点 |
| `external/` | 外部 PDF（Owner 自备） |

## 约定

- 只放**可入库**的参考资料（版权合规由 Owner 负责）。
- 优先 Markdown；PDF 由 `butler memory ingest` 转为 `.butler/ingest/*.md`。
- 勿放未脱敏密钥、私人通信原文。
- 参考书是**设定 SSOT 速查**，不替代 `04_正文/` 正史与 `workflow_state.json`。

## 入库

```bash
bash scripts/butler-ingest-pilot.sh
# 或
butler memory ingest --project 灵文1号 --reindex
butler memory search "暗皇值得吗" --scope project --project 灵文1号
```

## 与 novel-factory 边界

| 目录 | 层级 | 管什么 |
|------|------|--------|
| `novel-factory/references/` | L2 素材 | 静态参考文件 |
| `workflow_state.json` | L2 状态机 | 流水线阶段/批次 |
| `skill:webnovel-write` | L3 方法论 | 单章写作流程 |

Lead 答进度前仍须读 `workflow_state.json`；参考资料辅助检索与写作上下文。
