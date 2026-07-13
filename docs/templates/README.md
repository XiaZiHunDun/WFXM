# 文档模板索引

> **使用**：复制到 `.butler/` 或 `projects/<slug>/` 即可实例化。
> 模板与实例是**双源关系**：`docs/templates/*` 是源（可复用），`.butler/*` / 项目内文件是实例。

## 子目录

| 子目录 | 内容 | 何时用 |
|--------|------|--------|
| [`agents/`](agents/) | Agent profile 模板（如 [`code-explorer.md`](agents/code-explorer.md)） | 给管家/Lead/worker 定制 system prompt；复制到 `.butler/agents.md` |
| [`artifacts/`](artifacts/) | 实验 artifact 模板（[`README.md`](artifacts/README.md)） | 实验 harness 产物命名规范 |
| [`experiments/`](experiments/) | 实验 harness（[`README.md`](experiments/README.md) · [`PROGRAM.md`](experiments/PROGRAM.md) · `harness-eval.sh`） | 新功能 A/B 实验骨架 |
| [`project-archetypes/`](project-archetypes/) | `project.yaml` + runtime jobs 模板（`software-default` / `software-research` / `novel-factory` / `knowledge-light`） | `butler create <slug> --type <archetype>` 时套用 |
| [`skills/`](skills/) | Skill 模板（[`deep-research.md`](skills/deep-research.md) · [`design-system.md`](skills/design-system.md) · [`research-program.md`](skills/research-program.md)） | 复制到 `projects/<slug>/.butler/skills/` 启用 |

## 顶层文件

| 文件 | 用途 |
|------|------|
| [`permissions.yaml.example`](permissions.yaml.example) | 项目 `.butler/permissions.yaml` 模板（含 `workflow_steps`） |
| [`permissions-research.yaml`](permissions-research.yaml) | 研究类项目更宽权限变体（参考） |

## 实例在哪里

| 模板 | 实例路径 |
|------|----------|
| `agents/code-explorer.md` | `~/.butler/agents.md` 或 `projects/<slug>/.butler/agents.md` |
| `skills/*.md` | `projects/<slug>/.butler/skills/<name>.md` |
| `project-archetypes/<name>.project.yaml` | `projects/<slug>/project.yaml` |
| `permissions.yaml.example` | `projects/<slug>/.butler/permissions.yaml` |

## 维护规则

- 模板修改后须**同步至少一个实例**（或写明 "无实例依赖"），否则会漂移
- 实例化时用 `git mv` 保留历史（已 tracked 的源 → 实例）
- 新增 archetype → 同步在 `butler/cli/project_create.py` 的 `--type` 选项