# 项目能力模板（`project.yaml`）

复制对应文件到 `projects/<目录名>/project.yaml`，修改 `name`（微信 `/切换` 用显示名）、`description` 与 `tools`。

| 文件 | 适用 |
|------|------|
| `software-default.project.yaml` | 通用软件仓库 |
| `novel-factory.project.yaml` | 含 `novel-factory/` 与厂长模式 |
| `knowledge-light.project.yaml` | 仅文档/记忆，收紧工具 |

登记后运行：

```bash
butler project preflight --path projects/<目录名>
butler memory-reindex --project "<name>"
```

接入清单见 [`docs/guides/project-onboarding.md`](../../guides/project-onboarding.md)。
