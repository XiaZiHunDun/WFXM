# 面试 PPT 文字素材 · 索引

> WFXM 工作区面试专用素材库（2026-07 版）。**只深讲 1 个 Agent 项目**：WFXM Butler 框架本身。

## 文件夹结构

```
interview-ppt-2026-07/
├── README.md                  ← 本文件（索引）
├── 00-plan.md                 ← 生成计划 + 各文件大纲
├── cheat-sheet.md             ← A4 一页纸 cheat sheet（17 页版用，打印带去）
├── ppt-layout.md              ← 17 页 PPT layout 草图
├── 4-page-pitch/              ← 4 页浓缩版（HR 面 / 大会 lightning 用）
│   ├── README.md                  选页逻辑 + 何时用
│   ├── layout.md                  4 页 ASCII layout + 口播
│   ├── cheat-sheet-4p.md          半页纸 cheat sheet（4 页版用）
│   ├── p1-cover.md                P1 封面+痛点+Why Agent（S+T）
│   ├── p2-tech.md                 P2 架构+双挑战+关键代码（A）
│   ├── p3-proof.md                P3 量化+真实 Bug+Baseline（R）
│   └── p4-closing.md              P4 认知颠覆+标签回锚（L）
├── 01-wfxm-butler/            ← 深讲项目：WFXM Butler 框架
│   ├── 01-situation-task.md       S + T（痛点 / 必要性 / KPI / 角色）
│   ├── 02-action.md               A：6 大技术细节
│   ├── 03-result.md               R：量化 + Baseline 对比
│   ├── 04-learning.md             L：反思 + 认知颠覆
│   ├── 05-tech-tag.md             一句话技术标签
│   └── 06-architecture.mmd        Mermaid 架构图
├── diagrams/                  ← 跨章节共用图（mermaid 源码 + 已转 PNG）
│   ├── wfxm-architecture.mmd      整体架构
│   ├── tool-routing.mmd           跨进程工具路由（核心标签对应）
│   ├── memory-system.mmd          多源记忆治理（核心标签对应）
│   ├── wechat-integration.mmd     微信入口
│   └── runtime-jobs.mmd           调度 / runtime jobs
├── png/                       ← mermaid 转 PNG（1920x1080 @ 2x）
│   ├── wfxm-architecture.png
│   ├── tool-routing.png
│   ├── memory-system.png
│   ├── wechat-integration.png
│   ├── runtime-jobs.png
│   └── 06-architecture.png
└── talking-points/            ← 面试现场用
    ├── 01-opening-pitch.md        45-60 秒开场白
    ├── 02-deep-dive-script.md     3-5 分钟深讲口播稿
    ├── 03-common-qa.md            高频追问 Q&A（15 条）
    └── 04-whiteboard-guide.md     白板画法指南
```

## 使用方式

- **做 PPT**：`01-wfxm-butler/01-05` 直接对应 PPT 章节；`06-architecture.mmd` + `diagrams/*.mmd` 用 `mmdc` 或在线工具转图嵌入
- **面试现场**：`talking-points/` 是口播稿；白板画法在 `04-whiteboard-guide.md`
- **更新**：技术细节更新时改对应 `.md` 文件，无需重做 PPT

## 进度

- [x] 00-plan.md（生成计划）
- [x] 01-wfxm-butler/（6 文件）
- [x] diagrams/（5 文件 .mmd + 6 张 PNG 已转）
- [x] talking-points/（4 文件）
- [x] cheat-sheet.md（17 页版 A4 一页纸 cheat sheet）
- [x] ppt-layout.md（17 页 PPT layout 草图）
- [x] 4-page-pitch/（7 文件：README + layout + 4 个页面 + 4p cheat sheet）

**生成完毕**：2026-07-13，共 26 个文件 + 6 张 PNG（约 3500 行）。

## 版本选择

| 场景 | 用版本 |
|------|--------|
| HR 面 / 简历投递后第一轮 / 大会 lightning | **4-page-pitch/** |
| 技术初面（30-45 分钟） | 17 页版（ppt-layout.md + 01-wfxm-butler/） |
| 技术终面（1 小时+） | 17 页版 + cheat-sheet.md |
| 临时电梯（约到面聊） | **4-page-pitch/cheat-sheet-4p.md** 即可 |

## 关联

- 演示 backlog：`projects/LingWen1/docs/interview-demo-backlog.md`
- 演示文档：`projects/LingWen1/docs/interview-明天演示.md`
- 项目说明：`projects/README.md`