# G2-08 CA4 严格模式 Pilot — 设计 spec

> **For agentic workers:** 配套实施计划见 `docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md`（plan 阶段产出）。  
> **背景**：G2-08 在 `docs/plans/decisions/theory-implementation-gap-register-2026-06.md` 标"⏸️ 保持现状"（2026-06-13），但代码侧 `apply_coding_strict_pilot_gate` 已接线，文档侧 4 处与代码口径不一致。本 spec 把 G2-08 从 ⏸️ 转为"已接线 + 已跑通 pilot + 跑完退出严格"，给下次会话升级默认提供量化基线。  
> **优先级**：G2（G2-08 边界已接受 + opt-in 收口）；**影响面**：默认 `BUTLER_CODING_STRICT=0` 不变，pilot 期间临时打开，跑完恢复。

---

## 1. 目标

把 G2-08 从"理论有 + 代码有 + 文档未同步 + pilot 未跑"收敛为"理论-代码-文档-实证四对齐"：

1. **文档同步**：4 处文档口径与代码实现对齐（gap register / 理论 / config ref / roadmap）
2. **默认协调**：`effective_coding_strict_safe(default=True)` 与 `BUTLER_CODING_STRICT=0` 语义统一
3. **运维 enablement**：opt-in 脚本 + smoke，让主公/agent 可重复打开 strict
4. **机制实证**：Phase A 控型 smoke 验证 `apply_coding_strict_pilot_gate` 在 strict=1 + pilot 类别 + dev role + 违例非空时返 False
5. **量化基线**：Phase B 在灵文1号 ch001 复现任务上跑一次，统计违例捕获率 ≥ 85%
6. **退出 + 收口**：跑完退出严格；pilot 报告归档；4 文档可追溯；下次会话重拍是否升默认

---

## 2. 决策汇总（brainstorming 已确认）

| 维度 | 决策 |
|------|------|
| 范围 | 全套（6 阶段：G3 同步 + 默认协调 + opt-in + Phase A + Phase B + 退出） |
| Pilot 目的 | 机制验证 + 量化（两者兼有，分两阶段） |
| Sample | 仅灵文1号 ch001 复现任务 |
| 阈值 | 违例捕获率 ≥ 85%（与 G2-03 P-PIM live 门检 MiniMax 94% 同档） |
| 退出 | 跑完退出严格（默认回 0，下次会话重拍升默认） |

---

## 3. 现状与不一致

### 3.1 gap register 表述（v2026-06-13）

| 位置 | 原文 |
|------|------|
| §0 表行 37 | "`strict=1` 生产阻断**未接线**" |
| §2 表行 90 | "默认 `BUTLER_CODING_STRICT=0` advisory；`strict=1` 生产 pilot 类别 → `CODING_STRICT_GATE`；**⏸️ pilot opt-in**（2026-06-13）：默认 advisory；测评/灵文 sample 可 `strict=1` 观察" |
| §6 行 155 | "G2-08 保持现状：默认 advisory；`BUTLER_CODING_STRICT` env 未接生产阻断；opt-in 硬阻断 + CA4/delegate 关系待开发者详细理论分析后立项" |
| §6 行 159 | "G2-08 pilot：`CODING_STRICT_GATE` 接生产类别；B9 周循环增 `experience_selection_precision` + affinity backfill" |

### 3.2 代码现实（v2026-07-13）

| 维度 | 实现位置 | 状态 |
|------|----------|------|
| `apply_coding_strict_pilot_gate` 函数 | `butler/dev_engine/b9_delegate_gate.py:370-407` | ✅ 完整实现 |
| delegate 链接入 | `butler/tools/delegate_impl.py:323` | ✅ 已在 4-gate 链中调用 |
| 安全 getter | `butler/dev_engine/b9_delegate_gate_ops.py:64-95` | ✅ `coding_strict_enabled_safe` / `coding_strict_pilot_categories_safe` |
| env 默认值 | `butler/dev_engine/dev_tools.py:59-61` | ✅ 读 `BUTLER_CODING_STRICT` env 默认 `"0"` |
| init 默认值 | `butler/dev_engine/delegate_init_ops.py:64` | ⚠️ `effective_coding_strict_safe(default=True)` 与 env `"0"` 默认不一致 |
| pilot categories | `b9_delegate_gate_ops.py:91-94` fallback `{deep, quick, nexus-sprint}` + 优先 `PROD_PLAYBOOK_CATEGORIES` | ✅ |
| 观测 | `butler/ops/boundary_observability.py:410-416` | ✅ 已纳入 |
| 单元测试 | `tests/test_coding_knowledge_enhanced.py::test_coding_strict_default_off` | ✅ 已有 |

### 3.3 不一致结论

G2-08 实际属于 **G3（实现更优 / 文档同步）** + **小段运维 enablement + 实证 pilot**，不是 G2（边界未消）。
gap register §0 行 37 的"`strict=1` 生产阻断未接线"表述与代码现状不符，应同步为"已接线，待首次 pilot 实证"。

---

## 4. 设计（6 阶段）

### 阶段 1 — 文档同步（G3 收口）

**修改 4 文件**：

1. `docs/plans/decisions/theory-implementation-gap-register-2026-06.md`
   - §0 表行 37：从"⏸️ 保持现状"改为"✅ 已接线（2026-07-13）"；理由指向 commit + pilot report
   - §2 表行 90：从"⏸️ pilot opt-in"改为"✅ pilot opt-in + 首次实证（2026-07-13）"；附 pilot report 路径
   - §6 行 155：保留为变更记录
   - §6 行 159：保留为变更记录
   - 末尾新增 2026-07-13 变更行：G2-08 spec + plan + 6 commit + pilot report

2. `docs/architecture/v4-dev-engine-theory.md` §8.5 成熟度表
   - CA4 严格模式行 T1/T2/T3 升级（具体由 plan 阶段细化）
   - §9 CA4 公理处加"已 opt-in 实证"注

3. `docs/config/reference.md` `BUTLER_CODING_STRICT` 段
   - 现有描述保留；新增"已接入 `apply_coding_strict_pilot_gate`（2026-07-13）"
   - 附 pilot report 路径

4. `docs/plans/active/post-consolidation-roadmap-2026-05.md` §9 D3-10 行
   - 现有"D3-10 ✅ CA4 严格模式 + auto_verify 定理门"补一句"G2-08 pilot opt-in 实证 2026-07-13，捕获率 X%（详见 pilot report）"

**验收**：4 文件口径与代码一致；无"TODO 同步"残留。

### 阶段 2 — 默认协调

**修改 1 文件 + 1 新测试文件**：

1. `butler/dev_engine/delegate_init_ops.py:64`
   - `effective_coding_strict_safe(*, default: bool = True)` → `default: bool = False`
   - 同步：plan 阶段第一步 grep 调用点，确认仅 delegate_init 内部 1 处使用

2. `tests/dev_engine/test_coding_strict_default.py`（新建）
   - `test_effective_coding_strict_default_false_when_env_unset`：env 无 `BUTLER_CODING_STRICT` → 返 False
   - `test_effective_coding_strict_true_when_env_set`：env `BUTLER_CODING_STRICT=1` → 返 True
   - `test_effective_coding_strict_explicit_default_override`：调用时 `default=True` 覆盖 → 返 True

**验收**：3 单测通过；grep 确认无其他调用方受影响。

### 阶段 3 — 运维 opt-in 脚本 + smoke

**新建 2 文件**：

1. `scripts/butler-coding-strict-opt-in.sh`
   - 子命令：`on` / `off` / `status` / `audit`
   - `on`：写 `~/.butler/runtime/coding_strict_state.yaml` `{state: on, ts, by}`；追加 `~/.butler/audit/coding-strict-events.log` JSONL；提示下次启动进程生效
   - `off`：删 state 文件；追加 audit；清提示
   - `status`：读 state + 当前进程 env
   - `audit`：tail audit log

2. `tests/scripts/test_butler_coding_strict_opt_in_smoke.sh`（新建；可放 tests/scripts/ 沿用 P1#4 模式）
   - Case 1 `on_should_create_state_and_audit_entry`：调 `on` → 验 state 文件存在 + audit 追加 1 条
   - Case 2 `off_should_remove_state`：调 `off` → 验 state 文件不存在
   - Case 3 `status_should_report_on_or_off`：先 `on` 再 `status` → 期望 "on"；`off` 再 `status` → 期望 "off"
   - Case 4 `audit_should_tail_recent_events`：追加 2 条 event → `audit` 输出包含两条 ts

**验收**：4 case ALL PASS；state + audit 路径在 `~/.butler/` 下且与现有 `delegation-violations.log` 独立。

### 阶段 4 — Phase A 控型 smoke

**新建 1 文件**：

`scripts/butler-coding-strict-pilot-smoke.sh`（或并入 `tests/scripts/`）

- 设置 `BUTLER_CODING_STRICT=1`（用脚本临时设，验完清）
- Python inline：
  ```python
  from butler.dev_engine.b9_delegate_gate import apply_coding_strict_pilot_gate
  # Case 1: gate 阻断（strict=1 + dev + deep + violated）
  ok, issues = apply_coding_strict_pilot_gate(
      category='deep', role='dev',
      dev_engine={'coding_knowledge': {'violated': ['CA4', 'T8']}},
      base_success=True,
  )
  assert ok is False and any('CODING_STRICT_GATE' in i for i in issues)
  ```
- Case 1：strict=1 + dev + deep + violated 非空 → 阻断（False + `CODING_STRICT_GATE` in issues）
- Case 2：env 清掉（strict=0）→ 放行（True）
- Case 3：role=content → 放行
- Case 4：category=other（不在 pilot set）→ 放行

**验收**：4 case ALL PASS；case 1 必须阻断否则 Phase B 不能跑。

### 阶段 5 — Phase B 灵文1号 pilot

**新建 2 文件**：

1. `scripts/butler-coding-strict-pilot.sh`
   - env: `BUTLER_CODING_STRICT=1` + `BUTLER_ACTIVE_PROJECT=LingWen1`
   - 触发灵文1号 ch001 复现任务（具体方式 plan 阶段定：从 backlog 取首个 dev 项 / 人工指定）
   - 尾部解析 audit + 任务输出：
     - `violated_set` = `coding_knowledge.violated` 全集
     - `gate_events` = audit 中 `CODING_STRICT_GATE:` 出现次数
     - `捕获率` = |violated_set ∩ gate_blocked_ids| / |violated_set|
   - 写 `docs/plans/pilot-reports/pilot-report-G2-08-<date>.md`
   - exit 0（跑通）/ exit 1（任务崩溃 / 超时）

2. `docs/plans/pilot-reports/pilot-report-G2-08-<date>.md`（脚本产出）
   - 摘要：sample / env / ts / 捕获率 / 判定（达标 / 未达标）
   - 详细：violated ID 全集 + gate 阻断 ID + 未捕获 ID（如有）+ 偏差假设
   - 引用：`docs/architecture/v4-dev-engine-theory.md` §9 + `gap-register` §2

**验收**：跑通；报告含捕获率；未达标时不破坏现有维护态（不自动升默认）。

### 阶段 6 — 退出 + 收口

**1 个动作链**：

```bash
# 1. opt-in 退出
scripts/butler-coding-strict-opt-in.sh off

# 2. pilot-log 追加摘要
# 编辑 docs/plans/decisions/pilot-log.md §G2-08 段（如不存在则新建 §G2）

# 3. 黑板收口
# 写 .blackboard/shifts/<date>-<agent>-<NNN>.md
# append .blackboard/log.md
# 更新 .blackboard/tasks/backlog.yaml G2-08 → done（claim_ref）
# 更新 .blackboard/state.md

# 4. 提交一组黑板变更
git add .blackboard/shifts/<date>-<agent>-<NNN>.md .blackboard/tasks/backlog.yaml .blackboard/log.md .blackboard/state.md
git commit -m "blackboard: G2-08 pilot done + 班次卡"
```

**验收**：默认恢复；4 文档可追溯；下次会话可基于 pilot report 决策升不升默认。

---

## 5. 测试矩阵汇总

| 阶段 | 类型 | 数量 | 工具 |
|---|---|---|---|
| 2 | pytest | 3 | `tests/dev_engine/test_coding_strict_default.py` |
| 3 | bash smoke | 4 | `tests/scripts/test_butler_coding_strict_opt_in_smoke.sh` |
| 4 | bash smoke | 4 | `scripts/butler-coding-strict-pilot-smoke.sh` |
| 5 | 真实跑 | 1 | `docs/plans/pilot-reports/pilot-report-G2-08-<date>.md` |

阶段 1 + 6 是 commit-level 验证，不含独立测试。

---

## 6. 风险与未决

| 风险 | 缓解 |
|------|------|
| 阶段 2 改 `default=True` → `False` 影响未知调用方 | 阶段 2 第一步 grep `effective_coding_strict_safe` 调用点，plan 阶段列在 Task 1 |
| Phase B pilot 灵文1号 ch001 复现任务触发不到 dev delegate | plan 阶段先 dry-run 一次（strict=0）确认 delegate 链可达；触发方式由 plan 阶段定 |
| audit log 与 `delegation-violations.log` 命名/职责混淆 | 独立文件 `coding-strict-events.log`；spec §4 阶段 3 已注明 |
| 违例捕获率 < 85% 时的判定 | spec §4 阶段 5 已注明：报告标"未达标" + 偏差分析 + 不自动升默认 |
| pilot 跑挂时 workflow_state 污染 | 阶段 5 exit 1 不写报告；plan 阶段确认灵文1号 维护态可安全临时写回 |

---

## 7. 完成判据

- ✅ 阶段 1-5 全部 commit 落地
- ✅ 阶段 5 pilot report 存在且含捕获率
- ✅ 阶段 6 退出默认 + 黑板班次卡 + 4 文档同步
- ✅ 全测试矩阵通过（3 pytest + 4 bash + 4 bash = 11）
- ✅ gap register §0 行 37 + §2 行 90 标"✅"
- ✅ backlog.yaml G2-08 → done（with claim_ref）

---

## 8. 关联

- `docs/plans/decisions/theory-implementation-gap-register-2026-06.md` — G2-08 主登记册
- `docs/architecture/v4-dev-engine-theory.md` §9 CA4 — 公理定义
- `docs/config/reference.md` — env 默认值说明
- `docs/plans/active/post-consolidation-roadmap-2026-05.md` §9 — 路线图位置
- `docs/plans/decisions/pilot-log.md` §G2-08 — pilot 摘要（待新增）
- 黑板：`shifts/<date>-<agent>-<NNN>.md` + `tasks/backlog.yaml` G2-08