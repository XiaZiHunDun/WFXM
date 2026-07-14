# G2-08 Pilot Caveat — 2026-07-14

> **范围**：本 caveat 说明 G2-08 Phase B pilot **未真跑** 的原因 + 已验证基础设施清单，供下次会话决策。

---

## 1. 结论

| 维度 | 状态 |
|------|------|
| G3 文档同步（4 文件口径） | ✅ 已落地（commit `23fe0f57`） |
| 默认协调（`effective_coding_strict_safe(default=False)`） | ✅ 已落地（commit `7215a5a1`）+ 3 pytest 全过 |
| 运维 opt-in 工具（`scripts/butler-coding-strict-opt-in.sh`） | ✅ 已落地（commit `d554730b`）+ 4 bash smoke 全过 |
| Phase A gate 机制实证（`apply_coding_strict_pilot_gate` 4 case） | ✅ 已落地（commit `57067269`）+ 4 bash smoke 全过 |
| Phase B 真实 pilot（灵文1号 ch001） | ⏸️ **Deferred** — sample task 不存在于 `delegate_impl` registry |
| Pilot 阈值（85% 违例捕获率） | ⏸️ **N/A** — 无 sample 触发 |

---

## 2. 为什么 Phase B 没真跑

T6 实施阶段试图触发 `butler.tools.delegate_impl --task ch001-reproduce --role dev --category deep` 跑真实 pilot。代码审查发现：

1. **`ch001-reproduce` 不在 `butler.tools.delegate_impl` task registry 中**
   - grep 全代码库：仅 `workflow_state.json` 出现 `ch001` 字段（章节引用），无对应 dev delegate task 注册
   - `delegate_impl` 无 `main` 函数可直接调用
   - 真实可注册 task 应在 `butler.tools.delegate_impl` task map 中查找（例如 `coding-knowledge-fixup` / `delegate-init` 等）

2. **当前样本触发的行为**
   - `delegate_impl` 接到未知 task 名后，未报错退出（rc=0）
   - 但 stdout 为空，未走到 4-gate 链（`apply_coding_strict_pilot_gate` 未被触发）
   - 因此 `pilot-report` 即使写了，verdict 也是 `NO_VIOLATIONS`，**结构上无意义** — 不能作为 gate 实证

3. **决策（用户确认）**
   - 路径 A：**回退 T6（commit `505e81b2`）+ 接受基础设施实证** + 真 pilot 推迟
   - 不走路径 B（fixture 注入）：因为 spec §4 阶段5 明确要求"真实任务触发"，fixture 不算
   - 不走路径 C（找真实 task）：本次会话无足够上下文辨识哪个 task 能产出 `coding_knowledge.violated`；需要下次会话专门立项

---

## 3. 已验证基础设施细节

### 3.1 默认协调（commit `7215a5a1`）

| 文件 | 修改 |
|------|------|
| `butler/dev_engine/delegate_init_ops.py:64` | `effective_coding_strict_safe(*, default=False)` |
| `butler/dev_engine/coding_knowledge_fixup_ops.py:10` | 同上 wrapper 默认协调 |
| `tests/dev_engine/test_coding_strict_default.py` | 3 pytest：`env_unset` / `env_set` / `default_false` |

**验收**：3/3 pytest PASS。

### 3.2 运维 opt-in 工具（commit `d554730b`）

| 子命令 | 行为 | smoke case |
|--------|------|------------|
| `on` | 写 `~/.butler/runtime/coding_strict_state.yaml` + 追加 audit log | Case 1 |
| `off` | 删 state 文件 + 追加 audit log | Case 2 |
| `status` | 读 state + 当前 env | Case 3 |
| `audit` | tail audit log（最近 20 条） | Case 4 |

**验收**：4/4 bash smoke PASS。

### 3.3 Phase A gate 机制实证（commit `57067269`）

直接调 `apply_coding_strict_pilot_gate`，4 case：

| Case | env | role | category | violated | 期望 | 实测 |
|------|-----|------|----------|----------|------|------|
| 1 | strict=1 | dev | deep | `["CA4","T8"]` | 阻断 (False + `CODING_STRICT_GATE`) | ✅ PASS |
| 2 | strict=0 | dev | deep | `["CA4","T8"]` | 放行 | ✅ PASS |
| 3 | strict=1 | content | deep | `["CA4","T8"]` | 放行（role 不在 dev） | ✅ PASS |
| 4 | strict=1 | dev | other | `["CA4","T8"]` | 放行（category 不在 pilot set） | ✅ PASS |

**验收**：4/4 bash smoke PASS。

**结论**：gate 机制本身（`apply_coding_strict_pilot_gate` 行为）已通过 4 case 控型实证；但**未在真实任务链路上跑通**。

### 3.4 Phase B pilot runner 骨架（commit `d7a42913` + `ce397817`）

`scripts/butler-coding-strict-pilot.sh` 包含：
- opt-in 启用 strict
- env: `BUTLER_CODING_STRICT=1` + `BUTLER_ACTIVE_PROJECT=LingWen1`
- 触发 `delegate_impl` + 捕获 stdout/stderr
- 解析 `violated_set` ∩ `gate_blocked` → 计算精确捕获率
- 判定 verdict (MATCH / PARTIAL / NO_GATE / NO_VIOLATIONS / UNDETERMINED)
- 写 pilot-report 到 `docs/plans/pilot-reports/`

**本次修复**（紧跟 caveat）：脚本 bug — `set -uo pipefail` 下空 grep 触发 pipefail → set -e 退出，报告未写。所有 grep 末端加 `|| true` 兜底。

**现状**：runner 脚本语法 OK，可下次会话直接复用；只需替换 sample task。

---

## 4. 下次会话建议

1. **重新选 sample**：在 `butler.tools.delegate_impl` 现有 task map 中找一个 dev 任务，能真实产出 `coding_knowledge.violated` 字段（建议先 grep 现有 task 实现，看哪个在 `dev_engine.coding_knowledge.violated` 上有输出）
2. **dry-run 验证**：先 strict=0 跑一次，确认 stdout 含 `violated` 字段；再 strict=1 重跑，对比 gate 触发
3. **跑通后回填**：把 pilot report 写回 `docs/plans/pilot-reports/pilot-report-G2-08-<date>.md`，再用 4 文档口径同步补 commit
4. **决策升级默认**：基于真实 pilot 数据（≥ 85% 捕获率且 ≥ 2 个 sample），决定是否把 `BUTLER_CODING_STRICT` 默认从 0 升到 1

---

## 5. 关联

- spec: `docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md`
- plan: `docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md`
- pilot runner: `scripts/butler-coding-strict-pilot.sh`（已修 bug，语法 OK）
- opt-in tool: `scripts/butler-coding-strict-opt-in.sh`
- 4 文档口径同步 commit: `23fe0f57`
