# Workflow 变量 precedence（主线 O P2）

> 实现：`butler/workflows/variables.py`（`WorkflowVariablePool`）

## 插值语法

- 模板内使用 `{{step_id}}` 或 `{{step_id.output}}`（`output` / `result` / `summary` 等等价键由步骤 `outputs` 配置）。

## 写入顺序（后写覆盖先写）

1. 步骤执行完成后，`set_step_output(step_id, text, keys=...)` 写入池。
2. 同一步骤多 key：`step_id`、`step_id.output` 等并存；`get()` 先精确匹配再回退。

## 读取规则

| 引用 | 行为 |
|------|------|
| `{{foo}}` | 命中 `values["foo"]` 则替换，否则保留原文 |
| `{{foo.bar}}` | 仅当 `foo.bar` 整键存在时替换 |
| 空值 | 不替换（保留 `{{...}}` 占位符） |

## 与 rescue / replan 的关系

- **rescue** 步骤输出同样进入变量池（键为 rescue 步骤 id）。
- **dev-qa-loop QA FAIL replan** 会更新 implement 任务正文；qa 步骤仍通过 `{{implement.output}}` 读取上一轮 implement 输出（池内为最近一次 implement 结果）。

## 相关环境变量

- `BUTLER_WORKFLOW_QA_REPLAN` / `BUTLER_WORKFLOW_QA_REPLAN_MAX` — QA FAIL 后自动重跑 implement（见 [`external-agent-reports-capabilities-2026-05.md`](external-agent-reports-capabilities-2026-05.md)）。
