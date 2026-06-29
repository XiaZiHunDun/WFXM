# TCR strict 升级 Runbook（fast-gate flip）

> **目标**：将 `butler-pytest-fast-gate.sh` 内 TCR 从 `--warn-only` 升级为 `--strict`（阈值 98%）。  
> **日历默认**：`BUTLER_TCR_STRICT_AFTER=2026-07-27`（4 周稳定周报后）。  
> **登记**：[`agent-production-gap-2026-06.md`](../plans/active/agent-production-gap-2026-06.md)

## 状态机

| `tcr-strict-readiness.json` → `status` | 含义 | 动作 |
|--------|------|------|
| `wait` | TCR 绿，但日历未到 | 继续每周 `--weekly` 打卡；**不要** flip |
| `ready` | TCR 绿且日历已到 | 执行 apply + 验证 fast-gate |
| `fail` | strict 跑分未达标 | 修 TCR 语料/边界测试后再查 |

报告路径：`.butler/reports/tcr-strict-readiness.json`（由 readiness 脚本写入）。

## 每周（窗内）

```bash
bash scripts/butler-ops-cadence.sh --weekly
# 内含 butler-tcr-strict-readiness.sh（失败不阻断周运营）
```

或单独：

```bash
bash scripts/butler-tcr-strict-readiness.sh
```

预期（窗内）：`status=wait`，`days_until_flip` > 0，TCR rate ≥ 98%。

## 到日 flip（≥ 2026-07-27）

```bash
# 1. 确认 readiness（~2min，跑 strict TCR）
bash scripts/butler-tcr-strict-readiness.sh
# 预期最后一行 status=ready

# 2. 预演（不改文件）
bash scripts/butler-tcr-strict-apply.sh --dry-run

# 3. 应用
bash scripts/butler-tcr-strict-apply.sh

# 4. 验证 fast-gate 全绿
bash scripts/butler-pytest-fast-gate.sh
```

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_TCR_STRICT_AFTER` | `2026-07-27` | 允许 flip 的最早日期（YYYY-MM-DD） |
| `BUTLER_TCR_THRESHOLD` | `0.98` | TCR 阈值（见 `tcr_report.py`） |

## 回滚

若 flip 后 fast-gate 红：

```bash
sed -i 's/butler-trajectory-compliance-gate.sh --strict/butler-trajectory-compliance-gate.sh --warn-only/' \
  scripts/butler-pytest-fast-gate.sh
```

修完 TCR 后再按本文「到日 flip」重试。

## 相关

- `scripts/butler-trajectory-compliance-gate.sh` — TCR 跑分
- `.butler/reports/tcr-latest.json` — 最近一次 TCR 指标
- [`evaluation-guide.md`](evaluation-guide.md) — `butler eval run --suite tcr`
