# 用户项目工作区

`projects/` 存放 Butler 管理的**用户项目**（非框架代码）。每个子目录通常包含：

- `project.yaml` — 项目名、工具、工作流（**微信 `/切换` 用 `name` 字段，不是目录名**）
- 项目源码与资产
- `.butler/` — 会话、项目记忆（本地生成，已 gitignore）

## 当前项目

| 目录 | Butler 名称 | 说明 |
|------|-------------|------|
| [`LingWen1/`](LingWen1/) | **灵文1号** | WFXM 内小说工厂试点（含 `novel-factory/` 工作副本）；与正式灵文项目隔离 |
| [`DemoPilot/`](DemoPilot/) | **演示试点** | 轻量第二试点（多项目切换 / runtime 冒烟；无 novel-factory） |

创建新项目：`butler create <名称> --type software --description "..."`

**全局配置示例**：[`docs/config/config.yaml.example`](../docs/config/config.yaml.example) → 复制到 `~/.butler/config.yaml`
