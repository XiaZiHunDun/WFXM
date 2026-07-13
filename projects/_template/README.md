# `_template/` · 新项目 `stack.yaml` 模板源

> **角色**：Butler 运行时**基础设施依赖清单**（python_extras / host / apis / runtime / env_recommended）。
> **不**是项目能力配置（→ 见 [`../../docs/templates/project-archetypes/`](../../docs/templates/project-archetypes/)）。

## 与 `docs/templates/project-archetypes/` 的区别

| 文件 | 角色 | 何时复制 |
|------|------|----------|
| 本目录 `stack.yaml` | **基础设施清单**（python 依赖、host systemd 单元、apis、runtime jobs 路径、推荐 env） | `butler create <slug>` 时自动复制 → `projects/<slug>/stack.yaml` |
| [`../../docs/templates/project-archetypes/*-project.yaml`](../../docs/templates/project-archetypes/README.md) | **项目能力配置**（tools、workflow_steps、description、type） | `butler create --type <archetype>` 时套用 → `projects/<slug>/project.yaml` |

简言之：**`stack.yaml` = 框架运行时依赖**；**`project.yaml` = 项目业务能力**。两者互补。

## 实例

| 项目 | stack.yaml | project.yaml |
|------|------------|--------------|
| 灵文1号 | [`../LingWen1/stack.yaml`](../LingWen1/stack.yaml) | [`../LingWen1/project.yaml`](../LingWen1/project.yaml) |
| 普通试点项目 | ⚠️ **缺**（仅 project.yaml；运行时依赖检测会警告） | [`../DemoPilot/project.yaml`](../DemoPilot/project.yaml) |

DemoPilot 缺 stack.yaml 是已知状态；若 `butler doctor` 报 "stack.yaml missing"，按本模板补一份即可。

## 字段速查（节选自 `stack.yaml`）

| 段 | 用途 | 示例 |
|----|------|------|
| `python_extras.install` | 安装层级（`core` / `gateway` / `embedding` / `vectors` / `dev`） | `gateway` |
| `python_extras.includes` | 可选 extras 子集 | `[wechat, mcp, embeddings, vectors, web]` |
| `host[].name` / `unit` / `required` | systemd 单元（如 butler-gateway） | `{name: butler-gateway, unit: butler-gateway.service, required: true}` |
| `runtime.jobs` | runtime jobs.yaml 相对路径 | `projects/<目录名>/runtime/jobs.yaml` |
| `runtime.pack` | L2 pack 标识 | `<L2-pack-id>` |
| `env_recommended` | 推荐 env 变量与默认值 | `BUTLER_MCP_ENABLED: "1"` 等 |

完整字段约定见 [`../../docs/guides/dependency-terminology-2026-06.md`](../../docs/guides/dependency-terminology-2026-06.md)。

## 何时改本目录

- 新增 `python_extras` 类目（如 `whisper`、`ocr`）→ 改 `stack.yaml` 注释
- 新增 `host` 单元模板 → 改 `stack.yaml` `host` 段
- 调整 `env_recommended` 默认值 → 同步 [`../../docs/config/reference.md`](../../docs/config/reference.md) + `.env.example`

## 关联

- 依赖策略：[`../../docs/guides/dependency-policy-2026-05.md`](../../docs/guides/dependency-policy-2026-05.md)
- 项目接入：[`../../docs/guides/project-onboarding.md`](../../docs/guides/project-onboarding.md)
- 项目层规划（微信开发/测试/运行）：[`../../docs/architecture/project-layer-wechat-plan.md`](../../docs/architecture/project-layer-wechat-plan.md)