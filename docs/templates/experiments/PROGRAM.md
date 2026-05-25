# 研究项目 PROGRAM（software-research）

> 人类维护；Agent 只读执行。改假设与指标口径请更新本文件，不要改 `.butler/harness/`。

## 分支与目录

- **只读评测**：`.butler/harness/eval.sh`（或 `eval.py`）— 禁止 Agent patch
- **可写实验面**：`experiments/` — `BUTLER_EXPERIMENT_MODE=1` 时仅此目录可写
- **账本**：`.butler/experiments.tsv`（`keep` / `discard` / `crash`）

## 指标协议

- harness stdout 必须含一行：`METRIC <name>=<value>`（例如 `METRIC score=0.42`）
- runtime：`butler runtime run harness-eval --project <名>`
- 手动记账：`butler experiment record --project <名> --metric-value 0.5 --status keep`

## 简洁性

- 同等指标 → 更简单优先
- 连续 `crash` ≥ 3（同假设）→ 先修 harness，再改 `experiments/`

## 回滚（仅 CLI）

```bash
export BUTLER_EXPERIMENT_GIT_RESET=1
butler experiment best --project <名>
butler experiment discard --project <名> --apply-reset
```
