# 默认项目策略（C2）

> 微信 `/状态` 与 `/诊断` 均展示默认项目解析信息。

## 解析优先级

```text
1. 会话已绑定项目（/切换 或历史会话）
2. BUTLER_DEFAULT_PROJECT 环境变量
3. 无默认 → 提示 /切换 或 /项目 新建
```

## 配置

| 变量 | 说明 |
|------|------|
| `BUTLER_DEFAULT_PROJECT` | 新微信会话的默认项目**显示名**（与 `project.yaml` 的 `name` 一致） |
| `BUTLER_PROJECTS_DIR` | 项目根目录（默认 `projects/`） |

示例（灵文试点）：

```bash
BUTLER_DEFAULT_PROJECT=灵文1号
```

## 诊断

`/诊断` 输出块 **默认项目策略**：

- `BUTLER_DEFAULT_PROJECT` 当前值
- 本会话当前项目
- 解析说明（会话绑定 vs 环境默认）

实现：`butler/project/meta.py` → `format_default_project_policy_lines()`

## 相关

- [`project-onboarding.md`](./project-onboarding.md)
- [`phase5-multi-project-runbook.md`](./phase5-multi-project-runbook.md)
