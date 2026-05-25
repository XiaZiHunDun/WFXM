# 实验目录（software-research）

- **可写**：`experiments/` — Agent 在 `BUTLER_EXPERIMENT_MODE=1` 下仅能 patch/write 此目录。
- **只读**：`.butler/harness/` — 固定评测脚本；stdout 须含 `METRIC <name>=<value>`。
- **账本**：`.butler/experiments.tsv`（gitignore 由 `projects/*/.butler/` 覆盖）。
- **长日志**：`.butler/last_run.log`（job 输出超过行数阈值时自动写入）。

## harness 示例

```bash
chmod +x .butler/harness/eval.sh
.butler/harness/eval.sh
# 应打印: METRIC score=0.42
```

## CLI

```bash
export BUTLER_EXPERIMENT_MODE=1   # 启用路径守卫（可选）
butler runtime run harness-eval --project <name>
butler experiment list --project <name>
butler experiment best --project <name>
```

`discard` 回滚代码须显式：`BUTLER_EXPERIMENT_GIT_RESET=1` + `butler experiment discard --apply-reset`。
