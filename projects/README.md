# 用户项目工作区

`projects/` 存放 Butler 管理的**真实用户项目**（非框架代码）。每个子目录通常包含：

- 项目源码与配置
- `.butler/` — 会话、项目记忆等运行时数据（本地生成，勿提交敏感内容）

## 示例

| 目录 | 说明 |
|------|------|
| [`LingWen/`](LingWen/) | 灵文试点（小说工厂） |

创建新项目：`butler create <名称> --type software --description "..."`
