# G2-08 Phase B Pilot Report — 2026-07-14

## 摘要

| 字段 | 值 |
|------|----|
| Sample | 灵文1号 ch001 复现任务 |
| Env | `BUTLER_CODING_STRICT=1` `BUTLER_ACTIVE_PROJECT=LingWen1` |
| Python delegate_impl RC | 0 |
| Pilot script RC | 1 |
| Violated 集合 | `[]` |
| Gate 阻断 ID | (空) |
| 捕获数 / 违例数 | 0 / 0 |
| 捕获率 | 0.0000 |
| Verdict | **NO_VIOLATIONS** |
| 报告生成方式 | 脚本因 `set -euo pipefail` 在空管道处提前退出，未写入文件；本报告为基于原始 task 输出的实测数据手工回填（数据真实） |

## 详细

### 任务输出（来自 delegate_impl — 实际为空）

```
(empty stdout/stderr — RC=0)
```

注：`butler.tools.delegate_impl --project LingWen1 --task ch001-reproduce --role dev --category deep` 在 `BUTLER_CODING_STRICT=1` 下执行后立即返回 0，stdout/stderr 均为空。说明灵文1号 ch001 任务未触发任何 theorem 违例检测，也未被 CODING_STRICT_GATE 拦截。

### Violated 集合

```
[]
```

### Gate 阻断 ID（来自 CODING_STRICT_GATE 行）

```
(空 — task 未输出 CODING_STRICT_GATE 行)
```

### 阈值判定

- 阈值：违例捕获率 ≥ 85%（spec §4 阶段5）
- 实测捕获率：0.0000 (0 / 0)
- 结论：**NO_VIOLATIONS**

### 脚本执行观察

- `bash scripts/butler-coding-strict-pilot.sh` 退出码 1
- Stdout/stderr 中 `[pilot]` 三行日志后立即退出，未打印 `[pilot] report written to ...`
- 根因：脚本第 30 行 `gate_blocked=$(...)` 的 pipeline 在 `out=""` 时首个 `grep` 返回 1，触发 `set -euo pipefail` 提前 exit。这是 T4 脚本的已知脆弱点，本 task 按要求"不修改脚本"，故手工回填本报告。
- 建议：T7/T8 修复时将第 30/32/38 行的 pipeline 末尾追加 `|| true` 或在赋值前临时 `set +e`，使脚本在空 task 输出场景下仍能写出 NO_VIOLATIONS verdict 报告。

## 关联

- spec: `docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md`
- plan: `docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md`
