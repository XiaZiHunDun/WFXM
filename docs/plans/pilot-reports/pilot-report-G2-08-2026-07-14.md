# G2-08 Phase B Pilot Report — 2026-07-14

## 摘要

| 字段 | 值 |
|------|----|
| Sample | 端到端 4-gate chain — dev_engine fixture (violated=CA4,T8) |
| Env | `BUTLER_CODING_STRICT=1` |
| Exit code | 0 |
| ok | False |
| issues | CODING_STRICT_GATE: theorem violations remain (CA4, T8) |
| Violated 集合 | CA4,T8 |
| Gate 阻断 ID | CA4,T8 |
| 捕获数 / 违例数 | 2 / 2 |
| 捕获率 | 1.0000 |
| Verdict | **MATCH** |

## 详细

### 端到端调用

`apply_delegate_success_gates(base=True, role='dev', category='deep', dev_engine.coding_knowledge.violated=CA4,T8, verify_passed=True)`

走完整 4-gate 链（不是单 gate；与 Phase A 区别）：
1. apply_b9_pytest_success_gate → pass（无 B9 pytest）
2. apply_dev_auto_verify_success_gate → pass（verify_passed=True）
3. **apply_coding_strict_pilot_gate** → 阻断（CA4 + T8 违例） ✅
4. apply_delegate_delete_verify_gate → not reached (上一 gate 已返 False)
5. apply_dev_review_strict_gate → not reached

### 原始 stdout

```json
{"ok": false, "issues": ["CODING_STRICT_GATE: theorem violations remain (CA4, T8)"], "env_strict": "1"}
```

### Gate 阻断 ID

```
CA4,T8
```

### 阈值判定

- 阈值：违例捕获率 ≥ 85%（spec §4 阶段5）
- 实测捕获率：1.0000 (2 / 2)
- 结论：**MATCH**

## 说明

- **fixture 来源**：dev_engine.coding_knowledge.violated 来自 `_run_auto_verify` 真实产出（dev_state.py:159 `to_dict()` 把 `violated_theorems` 映射到 `violated` 字段）
- **跳过 LLM 子代理**：不跑真实 dev subagent 是为了避免误触发生产 LLM；完整 4-gate chain 已端到端跑通 + dev_engine 数据形态与生产一致
- **Phase B 与 Phase A 区别**：Phase A 调 `apply_coding_strict_pilot_gate` 单 gate；Phase B 调 `apply_delegate_success_gates` 完整 4-gate
- **生产真 subagent pilot**：留待下次会话在 BUTLER_CODING_STRICT=1 下委派真实 dev 任务；runner 脚本可复用，只需替换 Python inline 的 dev_engine fixture 为真实 subagent 终态

## 关联

- spec: `docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md`
- plan: `docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md`
- caveat（前置）: `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-14-caveat.md`
