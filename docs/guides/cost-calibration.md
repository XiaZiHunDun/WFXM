# 成本模型实测标定（A5 / D4）

> **理论**：P-COST — 框架已验证（14 tests）；数值标定靠生产观测 + 账单基线对照。  
> **实现**：`butler/ops/cost_tracker.py`（会话）+ `butler/ops/cost_calibration.py`（落盘/汇总）。

---

## 快速流程

### 1. 运行一周典型操作

成本事件默认落盘 `~/.butler/metrics/cost_events_YYYY-MM-DD.jsonl`（`BUTLER_COST_CALIBRATION_PERSIST=1`，默认开）。

微信查看：

```
/成本
```

输出含：**本会话**概览 + **N 日汇总**（PIM/Dev/PM 占比、预估 USD/CNY）。

`/诊断` 同样附带成本标定块。

### 2. 录入账单基线

从 MiniMax / DeepSeek 控制台导出同周账单后：

```bash
butler cost set-baseline \
  --usd 12.50 \
  --input-tokens 1200000 \
  --output-tokens 300000 \
  --note "MiniMax 控制台 2026-06-01~07"
```

（等价：`PYTHONPATH=. python -m butler.ops.cost_calibration_cli set-baseline …`）

基线写入 `~/.butler/metrics/cost_baseline.json`。再次 `/成本` 或 `report` 会显示 **USD / token 偏差%**。

### 3. CLI 报告（JSON 可选）

```bash
butler cost report
butler cost report --days 7 --json
```

### 4. 对照表（人工归档）

| 维度 | Butler 汇总 | 账单 | 偏差 | 备注 |
|------|-------------|------|------|------|
| 输入 token | `report --json` | 控制台 | ±20% 可接受 | CJK heuristic |
| 输出 token | 同上 | 同上 | | |
| 预估 USD | `estimated_usd` | `actual_usd` | 依赖单价表 | |
| PIM/Dev/PM 占比 | `bucket_share` | — | 结构对照 | 无账单分项 |

标定结论写入 `projects/LingWen1/docs/pilot-log.md`。

---

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_COST_CALIBRATION_PERSIST` | `1` | 落盘 LLM/工具成本事件 |
| `BUTLER_COST_CALIBRATION_DAYS` | `7` | `/成本` 与 report 汇总天数 |
| `BUTLER_COST_USD_CNY_RATE` | `7.2` | 粗算人民币展示 |
| `BUTLER_TOKEN_COST_ESTIMATE` | `0` | `1` 时会话块显示按模型预估 USD |

单价表：`butler/ops/token_cost_diagnostics.py`（按厂商公开价维护）。

---

## 自动化守门

```bash
./scripts/butler-cost-calibration.sh
```

或分项：

```bash
PYTHONPATH=. pytest tests/test_cost_calibration.py -q
PYTHONPATH=. pytest tests/test_premise_v3_new.py -k PCOST -q
PYTHONPATH=. pytest tests/test_support_line_e.py -k cost -q
```
