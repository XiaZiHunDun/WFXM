# BUTLER_CODING_STRICT 默认升级决策（Defer to G3 Observation）

> **Decision date**: 2026-07-14
> **Decision owner**: claude-code (with user ratification)
> **Status**: DEFERRED — 1-2 周观察窗口（G3）
> **关联**: G2-08 (pilot-log §G2-08), theory-implementation-gap-register §G2-08

---

## TL;DR

**决策**: BUTLER_CODING_STRICT 环境变量默认值**保持 "0"**（不改）。触发升级条件成熟后再从 "0" 翻到 "1"。

**触发**: G2-08 Phase B 端到端 4-gate chain 实证 — verdict MATCH, 捕获率 **100% (2/2)** 远超 85% 阈值。

**等待**: G3 观察窗口 1-2 周 — 累计 ≥3 个不同任务类型（content / dev / 其他）的真实 subagent pilot runs，目标 false positive 率 0，再二次拍板。

---

## 输入证据

| 来源 | 类型 | 结果 |
|---|---|---|
| G2-08 Phase A | 4 case 控型（直接调 `apply_coding_strict_pilot_gate`） | 4/4 PASS |
| G2-08 Phase A | opt-in smoke (bash 4 case: on/off/status/audit) | 4/4 PASS |
| G2-08 Phase B | 端到端 4-gate chain (`apply_delegate_success_gates`)，dev_engine fixture 与 `_run_auto_verify` 产出形态一致 | MATCH, **100% (2/2)** |
| pytest 矩阵 | `tests/dev_engine/test_coding_strict_default.py` | 3/3 PASS |
| Pilot runner | `scripts/butler-coding-strict-pilot.sh` 走真实 4-gate chain | 11/11 测试矩阵全过 |

证据形态：
- **Phase A** 验 gate 单点机制 ✅
- **Phase B** 验 4-gate chain 端到端 ✅（dev_engine fixture 是合成场景，不是真实 subagent）
- **真实生产 subagent pilot** 未跑（spec §4 阶段 6 留给下次会话，可复用 runner 脚本）

---

## 决策依据

### 为什么 **Defer** 而不是 **Now flip**

1. **2/2 sample 不足以估计 production false positive 率**
   - Phase B 是 dev_engine fixture 控型（`violated_theorems=['CA4','T8']` 硬编码注入），不是来自真实 subagent 终端状态
   - 真实生产里 CA4/T8 误报率是 0 还是 > 0 — 没有数据
   - 任何 false positive = 生产 dev task 阻塞 = 工时损失

2. **Default flip 是 production 级别动作**
   - `coding_strict_enabled()` 是 dev_engine 4-gate chain 入口的关键路径
   - env 默认从 "0" → "1" 后，所有 dev commit flow 走严格模式
   - 即便有 escape hatch（`BUTLER_CODING_STRICT=0` 临时禁用），回退事件本身需要被记录 + 复盘 — 这是 overhead
   - 当前默认 "0" 已经 infra verified，配齐了 escape hatch，不需要急着翻转

3. **Opt-in 路径已就位**
   - `scripts/butler-coding-strict-opt-in.sh on` 一键开启
   - `scripts/butler-coding-strict-pilot.sh` 跑实证 — 已验过
   - "想要严格的人" 已经能拿到严格模式

4. **Decision is reversible at low cost**
   - Defer 1-2 周 = 几乎 0 cost（opt-in 路径仍可用）
   - Now flip + wrong = 1-2 周 false positive 复盘 + 可能的 hotfix rollback

### 为什么不是 **Never flip**

- Phase B MATCH 不是"零证据"
- 100% 远超 85% threshold 是真信号 — gate 机制本身能区分 CA4/T8 违例
- 1-2 周观察后，证据更扎实再 flip 是合理的 progression
- 完全不 flip = 永远留着"未触发严格"事件累积，浪费已实证能力

---

## G3 观察窗口（1-2 周）

### 监控目标

1. **多任务类型覆盖**: ≥3 个不同任务类型（content / dev / 其他）的真实 subagent pilot run
2. **False positive 率**: 0（即任何 BUTLER_CODING_STRICT=0 临时回退事件需要被记录并复盘）
3. **累计 capture rate**: 在真实 subagent 终端下维持 ≥85% (与 G2-03 live 门检口径一致)
4. **Pilot-runner 重用**: 直接跑 `scripts/butler-coding-strict-pilot.sh`，把 Python inline 的 dev_engine fixture 替换为真实 `_run_subagent_loop` 终态

### 升级触发条件（满足任一即再拍）

- ✅ ≥3 任务类型，每个 ≥85% capture rate
- ✅ 0 false positive 回退事件
- ✅ 1-2 周观察完成（最长 14 天）

### 再决策路径（满足触发条件后）

```python
# butler/dev_engine/dev_tools.py:59-62
def coding_strict_enabled() -> bool:
    """CA4: strict mode — output only if both theorem + test pass."""
    raw = os.getenv("BUTLER_CODING_STRICT", "1")  # 0 → 1
    return raw.strip().lower() in ("1", "true", "yes")
```

同步：
1. `tests/dev_engine/test_coding_strict_default.py`: `test_coding_strict_env_unset_returns_false` → `test_coding_strict_env_unset_returns_true`
2. 跑测试矩阵：`pytest tests/dev_engine/test_coding_strict_default.py` + `bash scripts/butler-coding-strict-pilot.sh` → 全过
3. 4 文档口径同步：gap register §G2-08 / pilot-log §G2-08 / config/reference / v4-dev-engine-theory / post-consolidation-roadmap
4. 黑板收口：新 shift card + log 追加 + state.md 升级 + backlog 标 done

---

## 关联

- **Spec**: `docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md`
- **Plan**: `docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md`
- **Pilot report**: `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-14.md`
- **Pilot runner**: `scripts/butler-coding-strict-pilot.sh`
- **Opt-in script**: `scripts/butler-coding-strict-opt-in.sh`
- **Tests**: `tests/dev_engine/test_coding_strict_default.py`
- **Gap register**: `docs/plans/decisions/theory-implementation-gap-register-2026-06.md` §G2-08 row, §6 跑通行
- **Pilot log**: `docs/plans/decisions/pilot-log.md` §G2-08
- **Config**: `docs/config/reference.md` §BUTLER_CODING_STRICT
- **Theory**: `docs/architecture/v4-dev-engine-theory.md` §8.5 G2-08
- **Roadmap**: `docs/plans/active/post-consolidation-roadmap-2026-05.md` §G2-08 / D3-10

---

## 变更日志

- **2026-07-14**: 决策 defer + 观察窗口开启（claude-code 拍板，待用户 ratify）
