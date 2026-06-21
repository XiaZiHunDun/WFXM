# 《星陨纪元》参考书索引

> **用途**：Lead / 写章 Agent / 审查 Agent 的设定 SSOT 速查；纳入 EXT-3 语义检索。  
> **来源**：`03_内容仓库/01_全文总体大纲/`、`星陨纪元_优化版大纲`、已发布 v3.0 正文抽样核对。  
> **维护态**：全书 360 章已发布（S 级）；参考书用于**续写、修订、答疑、新书借鉴**，非替代正文。

## 文档清单

| 文件 | 内容 | 检索关键词示例 |
|------|------|----------------|
| [01-world-and-power-system.md](./01-world-and-power-system.md) | 世界观、境界、势力、地点、宇宙观 | 境界、星辰会、暗域、奇点 |
| [02-character-bible.md](./02-character-bible.md) | 主角/配角弧线、关系、形态日志 | 林夜、苏琳、小九形态、铁蛋 |
| [03-plot-timeline-foreshadowing.md](./03-plot-timeline-foreshadowing.md) | 三卷结构、时间轴、伏笔表 | T7 裂痕、黑鸦、金属片 |
| [04-writing-craft-checklist.md](./04-writing-craft-checklist.md) | 本项目文风与禁忌清单 | 废土氛围、情绪 S 级、AI 味 |
| [05-consistency-rules.md](./05-consistency-rules.md) | 已知的编号/状态/术语一致性问题 | 星月性别、境界对应、重复章 |
| [06-locations-atlas-vol1.md](./06-locations-atlas-vol1.md) | 卷1 地点志、地理扩张链 | 废土、雷城、星陨圣殿、枢纽城 |
| [07-items-artifacts.md](./07-items-artifacts.md) | 道具、信物、伏笔物件 | 金属片、猎刀、灵微机甲、黑鸦 |
| [08-locations-atlas-vol2-vol3.md](./08-locations-atlas-vol2-vol3.md) | 卷2–3 星际/宇宙地点志 | 星辰炼狱、虚无之渊、记忆之地 |
| [09-character-relationships-timeline.md](./09-character-relationships-timeline.md) | 人物关系与情感里程碑 | 裂痕和解、星月牺牲、十五年守候 |
| [mood-samples/vol1-tone-anchors.md](./mood-samples/vol1-tone-anchors.md) | 卷1 语气摘录 | 废土黄昏、守夜 |
| [mood-samples/vol2-tone-anchors.md](./mood-samples/vol2-tone-anchors.md) | 卷2 裂痕/和解摘录 | ch161 隐瞒、ch178 一起 |
| `external/` | Owner 自备竞品 PDF | 见 `external/README.md` |

## 与工厂其他目录的边界

| 路径 | 角色 |
|------|------|
| `novel-factory/references/` | **设定与规程**（本目录） |
| `03_内容仓库/04_正文/` | 已发布章节正文（不整书向量化） |
| `workflow_state.json` | 流水线阶段 / 批次（Lead 答进度必读） |
| `.butler/skills/webnovel-write/references/` | 通用写作方法论（Skill 注入） |
| `docs/research/` | 对外调研、竞品、平台策略 |

## 入库与检索

```bash
bash scripts/butler-ingest-pilot.sh
butler memory search "苏琳预言裂痕" --scope project --project 灵文1号
```

Markdown 可直接被 chunking 索引；PDF 放本目录后由 ingest 转为 `.butler/ingest/*.md`。

## Owner 可补充的外部素材

| 类型 | 建议放置 | 说明 |
|------|----------|------|
| 竞品 PDF | `references/external/` | 版权自负；仅摘录不入正文 |
| 情绪参考片段 | `references/mood-samples/` | 自写或已授权短段 |
| 平台规则 | `docs/research/` | 连载规范、审核红线 |
