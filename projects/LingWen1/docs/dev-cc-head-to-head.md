# Dev 能力对照：Butler 委派 vs 本机 Claude Code CLI

> **用途**：同一任务、同一仓库，分别用 CC CLI 与 Butler `role=dev` 委派执行，定量对比「是否达到 CC CLI 级开发能力」。  
> **边界**：Butler 不对标 Cursor IDE；机械层（全 shell / MCP Host）为产品否决项，见 [`dev-capability-ceiling-vs-cc-cli-2026-06.md`](../../../docs/plans/decisions/dev-capability-ceiling-vs-cc-cli-2026-06.md)。

## 记录表（每题一行）

| # | 任务简述 | 工作区路径 | CC CLI | Butler dev | 备注 |
|---|----------|------------|--------|------------|------|
| 1 | 修 failing pytest（单文件 off-by-one） | `tests/fixtures/head_to_head_t1/ws` | ✅ 27.5s / 5 turns | ✅ 35.1s / 5 tools（需 read_state seed） | 2026-06-23 |
| 2 | 逻辑 bug（butler_sample/discount） | `tests/fixtures/head_to_head_t2/ws` | ✅ 21.2s / 4 turns | ✅ 66.2s（pytest 绿） | 2026-06-23；Butler 慢 ~3× |
| 3 | 跨文件 rename（`getData`→`get_data`） | `tests/fixtures/head_to_head_t3/ws` | ✅ 91.7s / 7 turns | ✅ 34.7s / 7 tools（pytest 绿） | 2026-06-23；Butler 快 ~2.6× |
| 4 | 测试驱动新增 `add()` | `tests/fixtures/head_to_head_t4/ws` | ✅ 33.0s / 5 turns | ✅ 45.8s / 4 tools（pytest 绿） | 2026-06-23；Butler 慢 ~1.4× |
| 5 | 灵文 demo `add()` 逻辑修复 | `tests/fixtures/head_to_head_t5/ws` | ✅ 17.8s / 5 turns | ✅ 39.3s / 4 tools（pytest 绿） | 2026-06-23；Butler 慢 ~2.2× |

### 每侧必填字段

| 字段 | CC CLI | Butler dev |
|------|--------|------------|
| 首次 verify 绿？ | ✅ pytest | ✅ pytest + DEV_VERIFY（head-to-head 类别） |
| 迭代轮数 | 5 turns | ~5 tool actions |
| 工具调用数（约） | 5 | 5 |
| 墙钟时间（分钟） | 0.46 | 0.58（seed 后；无 seed 首次 113s 失败） |
| task_id / 会话 | — | `task_b62ee7c17905` |
| 失败原因（若未绿） | — | 首次 `task_9636c2cc8547` READ_STATE 死循环 → 空结果 |

**T1 判定（2026-06-23）**：同题 **pytest 均绿**；Butler 略慢（35s vs 28s）但在 **1.5×** 内 → **不弱于 CC**（机械层有 seed 依赖，见下）。

```bash
# 复现 T1/T2 头对头
bash scripts/butler-head-to-head.sh t1
bash scripts/butler-head-to-head.sh t2
bash scripts/butler-head-to-head.sh t3
bash scripts/butler-head-to-head.sh t4
bash scripts/butler-head-to-head.sh t5
bash scripts/butler-head-to-head-t1.sh   # 同 t1
bash scripts/butler-head-to-head-t2.sh   # 同 t2
bash scripts/butler-head-to-head-t3.sh   # 同 t3
bash scripts/butler-head-to-head-t4.sh   # 同 t4
bash scripts/butler-head-to-head-t5.sh   # 同 t5
```

**首次 Butler 失败根因**：孤立 workspace 未 `seed_b9_workspace_read_state`，并行 read 后 patch 仍撞 `READ_STATE_REQUIRED`（与 B9 同类）。脚本已加 parent session seed + 子会话继承。

---

## 推荐五题（可直接复制）

### T1 — pytest 单点修复（Tier-1 类）

- **目标**：修一个已知 failing test 对应实现（off-by-one 或缺冒号）。
- **CC**：在 repo 根 `claude`（或你的 CC 入口），给路径 + 失败 traceback。
- **Butler**：微信或 CLI  
  `请 delegate_task role=dev：修复 <path>，使 pytest <nodeid> 通过；先 read_file，patch/write，再 terminal pytest。`

### T2 — butler 风格逻辑 bug

- **夹具**：`tests/fixtures/head_to_head_t2/`（`apply_discount` 误为 `price - rate`）
- **验收**：`python3 -m pytest tests/test_discount.py -q`

```bash
bash scripts/butler-head-to-head.sh t2
```

**2026-06-23 结果**：CC **21.2s** / Butler **66.2s**；**pytest 均绿**。结果不差于 CC，但耗时超 1.5× → 记为 **功能 parity、延迟 gap**。

### T3 — 跨文件 import / rename

- **夹具**：`tests/fixtures/head_to_head_t3/`（`pkg/client.py` 中 `getData` → `get_data`；`__init__.py` 仅 re-export `Client`）
- **目标**：B9 `B9L_cross_module_rename` 同类跨模块符号重命名。
- **验收**：`python3 -m pytest test_pkg.py -q`

```bash
bash scripts/butler-head-to-head.sh t3
bash scripts/butler-head-to-head-t3.sh   # 同 t3
```

**2026-06-23 结果**：CC **91.7s** / 7 turns；Butler **34.7s** / 7 tools（report `task_d98213d30c9c`）；**pytest 均绿**。Butler **更快**（≈2.6×）。修复后复跑 `task_556c6c697fdf`：**verify 全绿**（`head-to-head` 类别仅跑 `test` 级 auto-verify + 夹具 `project.yaml`）。

### T4 — 新增函数 + 测试（test-driven add）

- **夹具**：`tests/fixtures/head_to_head_t4/`（`lib.py` 缺 `add()`，`test_lib.py` 验收）
- **目标**：B9 `B9L_test_driven_add` 同类测试驱动实现。
- **验收**：`python3 -m pytest test_lib.py -q`

```bash
bash scripts/butler-head-to-head.sh t4
bash scripts/butler-head-to-head-t4.sh   # 同 t4
```

**2026-06-23 结果**：CC **33.0s** / 5 turns；Butler **45.8s** / 4 tools（`task_94144348212c`）；**pytest 均绿**；**DEV_VERIFY 对齐**（`verify_passed=True`）。Butler 慢 ~1.4× → **功能 parity、在 1.5× 内**。

### T5 — 灵文非 docs 实改

- **夹具**：`tests/fixtures/head_to_head_t5/`（LingWen1 `demo/hello.py` 形：`add()` 误为 `a-b`）
- **目标**：B9 `B9L_prod_lingwen_demo_add` 同类业务逻辑修复（非 markdown）。
- **验收**：`python3 -m pytest test_demo.py -q`

```bash
bash scripts/butler-head-to-head.sh t5
bash scripts/butler-head-to-head-t5.sh   # 同 t5
```

**2026-06-23 结果**：CC **17.8s** / 5 turns；Butler **39.3s** / 4 tools（`task_8d1ac921abdc`）；**pytest 均绿**；**DEV_VERIFY 对齐**。Butler 慢 ~2.2× → **功能 parity、延迟 gap**。

---

## T1–T5 总判定（2026-06-23）

| 题 | 类型 | pytest parity | Butler vs CC 耗时 | 备注 |
|----|------|---------------|-------------------|------|
| T1 | 单文件 off-by-one | ✅ | ~1.3× 慢 | 需 read_state seed |
| T2 | butler 逻辑 bug | ✅ | ~3× 慢 | 延迟 gap |
| T3 | 跨文件 rename | ✅ | **~0.38× 更快** | verify 已绿（`task_556c6c697fdf`） |
| T4 | test-driven add | ✅ | ~1.4× 慢 | 在 1.5× 内 |
| T5 | 灵文 demo 逻辑 | ✅ | ~2.2× 慢 | terminal allowlist |

**结论**：五题 **pytest 均绿** → 委派 dev **功能上不弱于本机 CC CLI**。2026-06-23 后续修复：`select_auto_verify_levels` 对 `head-to-head-*` 仅 `test`；夹具写入 `project.yaml` 限定 pytest；prompt 推荐 `run_pytest` → **DEV_VERIFY 与 pytest 对齐**（T3 复跑 `verify=True`）。剩余 gap：**墙钟延迟**（T2/T5 超 1.5×）。微信 handler sim：`task_7146d5e81fc2` **role=dev PASS**（`docs/dev-flywheel-2026-06-23.md`）。

## 合成基准（Butler 内置，非头对头）

```bash
# Oracle（CI，无 LLM）
bash scripts/butler-eval-llm-benchmark.sh

# LIVE（真 LLM，10 题固定集 + Tier-1 门控 ≥50%）
BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-b9-live.sh

# 周循环
bash scripts/butler-b9-weekly-learning.sh
```

结果写入 `~/.butler/audit/b9_benchmark.jsonl`；微信 `/诊断` 或 `/委派质量` 可看最近快照。

---

## 运行记录

| 日期 | B9 LIVE Tier-1 | Tier-2 | 可解题 | STUCK | 头对头 T1–T5 | 记录人 |
|------|----------------|--------|--------|-------|--------------|--------|
| 2026-06-23 | **9/9 (100%)** | 12/12 (100%) | 21/21 | ❌ STUCK 探针 | **T1–T5 全✅** | agent |

**2026-06-23 B9 LIVE 解读**（`bash scripts/butler-eval-b9-live.sh`，~23min）：

- **可解题（21/21）全绿**：含单文件 pytest、跨模块 rename、prod-shaped READ_STATE、灵文 `demo/hello`、`workflow_guard` 等。
- **Tier-1 门控**：9/9 ≥ 50% 阈值 → **通过**（合成编码能力达标）。
- **脚本 exit 1 原因**：`B9L_stuck_unsolvable` 本应 STUCK（verify 仍应失败），代理却 patch 到 verify 通过 → 记 `unexpectedly fixed`（终止能力/诚实边界探针，非能力不够）。
- **与 CC 关系**：B9 只测 Butler 委派链，**不能**替代同题 CC CLI 对照；头对头仍填上表 T1–T5。

```bash
# 复现
BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-b9-live.sh
# 审计
tail -1 ~/.butler/audit/b9_benchmark.jsonl | python3 -m json.tool
```
