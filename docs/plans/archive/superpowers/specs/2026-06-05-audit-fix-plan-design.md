# WFXM 8 轮审计 C/H 修复方案

> **设计日期**:2026-06-05
> **对应审计**:`docs/reviews/project-deep-audit-2026-06-r1to8.md`(138 条 = 22 C + 46 H + 50 M + 20 L)
> **状态**:设计批准,待 writing-plans
> **作者**:Claude (brainstorming skill)

---

## 1. 背景与目标

### 1.1 8 轮审计产出

2026-06-05 完成的 8 轮深度审计覆盖架构/错误处理/安全/并发/资源/测试/文档/配置 8 个维度,共 138 条发现(已排除 9 条误报或重复,实际 138/147 = 93.9% 命中率):

| 维度 | Round | C | H | M | L |
|------|-------|---|---|---|---|
| 架构 | R1 | 4 | 8 | 8 | 0 |
| 错误处理 | R2 | 8 | 11 | 2 | 0 |
| 安全 | R3 | 0 | 3 | 0 | 1 |
| 并发 | R4 | 3 | 4 | 1 | 0 |
| 资源 | R5 | 4 | 6 | 1 | 0 |
| 测试 | R6 | 1 | 3 | 0 | 4 |
| 文档 | R7 | 1 | 7 | 2 | 2 |
| 配置 | R8 | 1 | 4 | 5 | 0 |
| **合计** | | **22** | **46** | **50** | **20** |

### 1.2 目标

1. **修复 22 C + 46 H = 68 条**(本设计范围)
2. **defer 50 M + 20 L = 70 条**(不修,仅当 C/H 修复顺势覆盖时才一并处理)
3. 修复后审计 doc grep 验证:`R[1-8]-N [CH]` 仅返回 0 行
4. 全部代码类 C/H 必须 RED→GREEN 测试证据;文档/配置类豁免 RED test
5. 8 PR 可独立 merge(单 PR 内 commit 单独可 cherry-pick / revert);PR 间因文件重叠(见 §3 预警),不可独立 cherry-pick

---

## 2. 设计决策(用户已确认)

| # | 决策点 | 选定 | 理由 |
|---|--------|------|------|
| 1 | 范围 | C+H(68 条) | C+H 是合并阻塞;M/L 不阻塞 release |
| 2 | 批次 | 按 round 拆 8 PR | 风险按维度隔离,reviewer 认知负担最小 |
| 3 | Commit 粒度 | 1 commit / issue(共 68 commit) | 细粒度便于 cherry-pick / blame / revert |
| 4 | 测试要求 | 代码 C+H 必 RED,文档/配置 C+H 免 | 与 issue 类型匹配,不强制文档 issue 写测试 |
| 5 | 执行模式 | Subagent-driven | 主线程节约 context,subagent 隔离污染 |
| 6 | 执行变体 | **A:1 issue / subagent,串行 8 PR** | 严格串行最稳;每 issue 双 review 控质量 |

---

## 3. 工作分解(8 PR × 68 commits)

每个 PR 处理一个 round 的全部 C/H,在独立分支上线性 commit:

| PR | 分支 | Round | 维度 | C | H | Commits | 风险点 |
|----|------|-------|------|---|---|---------|--------|
| PR-1 | `fix/r1-arch` | R1 | 架构 | 4 | 8 | **12** | R1-4 wechat_ilink.py 2027 行拆分(可能触发拆分开关) |
| PR-2 | `fix/r2-errors` | R2 | 错误处理 | 8 | 11 | **19** | 最大批量;含 R2-19 12+ 状态文件统一修复(可能触发拆分开关) |
| PR-3 | `fix/r3-security` | R3 | 安全 | 0 | 3 | **3** | R3-2 RCE 链需联合修改 hooks/loader + path_safety |
| PR-4 | `fix/r4-concurrency` | R4 | 并发 | 3 | 4 | **7** | R4-7 跨 loop 共享(wechat_ilink)与 R1-12 文件重叠 |
| PR-5 | `fix/r5-resources` | R5 | 资源 | 4 | 6 | **10** | R5-2/3 db_leak 涉及 sqlite + ChromaDB close |
| PR-6 | `fix/r6-tests` | R6 | 测试 | 1 | 3 | **4** | **R6-11 baseline 失败作为首项** |
| PR-7 | `fix/r7-docs` | R7 | 文档 | 1 | 7 | **8** | R7-1 BUTLER_ONBOARDING_WELCOME 三处矛盾 |
| PR-8 | `fix/r8-config` | R8 | 配置 | 1 | 4 | **5** | R8-3 load_dotenv import-time |
| | | | | **22** | **46** | **68** | |

**文件重叠预警**:
- `wechat_ilink.py` 涉及 R1-4(god)、R1-12(mutable)、R4-7(async):R1 PR 拆,后续 R4 PR 仅改并发相关行
- `agent_loop.py` 涉及 R1-2(layering)、R1-8(god)、R2-9(17 个 except):R1 先拆 + 解耦,R2 再改 except
- `read_state.py` 涉及 R4-5(lock)、R5-8(unbounded_cache):R4 PR 改锁,R5 PR 改 cache 边界

---

## 4. 每 Issue 生命周期

每个 issue 走 4 步流水线,主线程调度,subagent 执行:

```
Step 1: Implementer subagent
  ├─ 输入(主线程构造):
  │   - issue ID + 审计原文(精确 file:line)
  │   - 测试模式参考(同目录最近 1-2 个 test_*.py 片段)
  │   - commit 模板: `<type>: R{n}-{id} {中文标题}`
  │   - 严禁:修改 issue 范围外代码 / 顺手修 M/L / 自创 commit 标题
  ├─ 代码 C/H:
  │   - RED: 写失败测试,跑 pytest 确认失败
  │   - GREEN: 最小修复,跑 pytest 确认通过
  │   - Refactor: 清理(可选)
  │   - 全部 pytest 不能让 baseline gate 变红
  ├─ 文档/配置 C/H:
  │   - 直接改文档/.env.example
  │   - 无需 RED,但需 1 个 grep/手动验证作为"事实"证据
  └─ Commit:
      - type ∈ {fix, refactor, docs, test, chore}
      - 格式:`fix: R1-4 拆分 wechat_ilink.py god module (R1-4 拆分)`

Step 2: Spec-compliance reviewer subagent
  ├─ 输入:git diff 范围(本次 commit) + issue ID + 审计原文
  ├─ 检查清单:
  │   □ 改动是否真正解决审计 issue?
  │   □ 是否动到 issue 范围外?(用 git diff --stat 与审计 file:line 对比)
  │   □ 是否顺手修 M/L?(若在 diff 中,标记 spec 失败)
  └─ 不通过 → 回到 Step 1 重派 implementer 修复;重审直到通过

Step 3: Code-quality reviewer subagent
  ├─ 输入:git diff 范围 + 项目现有模式(主线程提供 1-2 个参考文件)
  ├─ 检查清单:
  │   □ 命名/可读性(PEP 8、类型注解)
  │   □ 错误处理是否引入新的 silent pass / log_continue(避免 R2 类问题)
  │   □ 与现有模式一致(看邻近 1-2 文件)
  │   □ 函数 < 50 行 / 文件 < 800 行(维持基线)
  └─ 不通过 → 回到 Step 1 重派 implementer 修复;重审直到通过

Step 4: 主线程标记 issue 完成,派下一个
```

**子 agent 协议统计:**
- 总调用数:68 issue × 3 subagent = **204 次**
- Implementer 平均耗时估算:5-10 min/issue(代码 C/H 较慢,文档较快)
- Reviewer 平均耗时估算:2-3 min/issue
- 串行总耗时估算:8-12 小时(含排队 + pytest 跑批 + 重审)

---

## 5. 执行顺序

### 5.1 PR 间顺序(严格串行)

```
main ──branch off──→ fix/r1-arch ──commit×12──→ merge ──branch off──→ fix/r2-errors ──commit×19──→ merge ...
                                                                                                            ↓
                                                                                                       fix/r8-config ──merge
```

- 起点:每个 PR 从最新 `main` 拉
- 终点:该 round 全部 C/H 完成 + pytest 全绿 + 双 review 通过 + 推送分支 + 创建 PR
- 不并发:8 PR 严格串行,避免后序 round 引用前序 round 改动

### 5.2 PR 内顺序

- 线性 commit,无 merge commit
- 顺序:同 PR 内**先 C 后 H**(C 修复引入回归风险更大,优先暴露)
- 顺序例外:依赖关系强制拓扑(主线程在派工前手绘依赖图)

### 5.3 测试回归监测点

- PR-6 首项即 R6-11 baseline 修复(整个 baseline gate 系统)
- 每 5 commit 重跑 `pytest tests/ -x` 一次,避免长尾回归
- 任一 PR 完成时跑全 suite,主线程判断是否触发"回滚开关"

---

## 6. 风险与降级

| # | 风险 | 触发条件 | 降级方案 | 开关 |
|---|------|---------|---------|------|
| R-A | R2 过大(19 commit) | PR-2 diff 累计 > 3000 行 | 拆 `fix/r2a-errors-core`(前 10)+ `fix/r2b-errors-edge`(后 9) | 拆分开关 |
| R-B | R6-11 baseline 回归 | pytest 中 baseline gate 变红 | PR-6 首项直接修;跑全 suite 而非单文件;每 5 commit 重跑 | 回滚开关 |
| R-C | subagent 漂移(改错文件) | spec review 发现动错位 | 重派 implementer,提供精确 file:line;严禁 subagent 自己 grep 全树 | 重审 |
| R-D | 跨 issue 依赖 | 某 issue 测试需要前 issue 的代码 | 主线程派工前手绘依赖图,subagent 收到 topological order | 顺序调整 |
| R-E | reviewer 反复打回 | 同一 issue 累计 subagent > 6 次未通过 | 主线程介入读代码,跳过 subagent 直接修 | 暂停开关 |
| R-F | M/L 越界修复 | subagent 顺手修 L/M | spec review 第一条卡:检查 `git diff --stat`,不在本 PR 范围 revert | 重审 |
| R-G | commit message 漂移 | subagent 自创标题 | 主线程提供强制 commit 模板,subagent 必须填占位符 | 重审 |

### 6.1 主线程三开关(明确阈值)

| 开关 | 阈值 | 触发后动作 |
|------|------|----------|
| **暂停开关** | 同一 issue 累计 subagent 调用 > 6 次 | 暂停自动流水线,主线程读代码+直接改 |
| **拆分开关** | 同一 PR 累计 commit > 20 或 diff > 3000 行 | 暂停 PR,拆 sub-PR 重新派工 |
| **回滚开关** | 跑完 pytest 有 baseline 变红 | 暂停,定位首个引入 commit,revert 或修复 |

---

## 7. 验证标准

每个 PR 完成时验证(主线程执行):

1. `grep -E "^\*\*R{n}-[0-9]+ \[[CH]\]" audit.md` → 该 round 计数应为 0
2. `pytest tests/ -x` → 全绿
3. `git log --oneline main..HEAD` → commit 数 = 该 round 的 C+H 计数
4. `git diff main...HEAD --stat` → 不含该 round 范围外文件
5. 推送分支 + 创建 PR 描述(含审计 ID → commit hash 映射表)

整体完成(8 PR 全 merge)验证:
- `grep -cE "^\*\*R[1-8]-[0-9]+ \[[CH]\]" audit.md` → 0
- `pytest tests/` → 全绿
- 主分支 8 个独立 commit 流可 cherry-pick

---

## 8. 附录:68 条 C/H 完整列表

来源:`docs/reviews/project-deep-audit-2026-06-r1to8.md`(grep 核对,2026-06-05)

### R1 架构(12 条 = 4C + 8H)

| ID | Sev | 类型 | 文件 |
|----|-----|------|------|
| R1-1 | C | layering_violation | `butler/transport/llm_client.py:360, 383, 476` |
| R1-2 | C | layering_violation | `butler/core/agent_loop.py:143` |
| R1-3 | C | layering_violation | `butler/core/context_compressor.py:426`, `compaction_task.py:80,130,162`, `compaction_steer_bridge.py:33` |
| R1-4 | C | god_module | `butler/gateway/platforms/wechat_ilink.py`(2027 行,90 函数) |
| R1-5 | H | god_module | `butler/tools/delegate_impl.py:237-645` |
| R1-6 | H | god_module | `butler/gateway/message_handler.py` |
| R1-7 | H | god_module | `butler/main.py:999-1317` |
| R1-8 | H | god_module | `butler/core/agent_loop.py:250-587` |
| R1-9 | H | layering_violation | `butler/transport/stream_probe.py:52` |
| R1-10 | H | layering_violation | 7 个 tools 模块反向 import gateway |
| R1-11 | H | module_mutable | `butler/core/exp_cache.py:23-24, 92-129` |
| R1-12 | H | module_mutable | `butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058, 1956` |

### R2 错误处理(19 条 = 8C + 11H)

| ID | Sev | 类型 | 文件 |
|----|-----|------|------|
| R2-1 | C | log_continue | `butler/skills/consolidator.py:96-98` |
| R2-2 | C | log_continue | `butler/memory/semantic_index.py:413-414, 458-459, 473-474` |
| R2-3 | C | log_continue | `butler/memory/embedding.py:251-252, 345-350` |
| R2-4 | C | silent_disable | `butler/orchestrator.py:208-210` |
| R2-5 | C | bad_fallback(SSRF 降级) | `butler/registry/install_scan.py:120-125` |
| R2-6 | C | log_continue | `butler/mcp/manager.py:171-179` |
| R2-7 | C | log_continue | `butler/session/post_session.py:357-358, 412-413` |
| R2-8 | C | log_continue(debuggability killed) | `butler/skills/manager.py:107-122` |
| R2-9 | H | log_continue | `butler/core/agent_loop.py:214, 227, 238, 364, 423, 552, 701, 786` |
| R2-10 | H | bad_fallback | `butler/transport/llm_client.py:149-150, 211-212` |
| R2-11 | H | log_continue(enforcement layer 失守) | `butler/permissions/rules.py:51, 87, 405, 488, 503` |
| R2-12 | H | bad_fallback(state corruption mask) | `butler/registry/mcp_merge.py:147-149` |
| R2-13 | H | log_continue(security signal silenced) | `butler/skills/manager.py:227-228` |
| R2-14 | H | log_continue(主 dedup 机制失效) | `butler/skills/similarity.py:218-221` |
| R2-15 | H | log_continue(SSRF 降级) | `butler/registry/skill_sources/github.py:115-126, marketplace.py:107-108, 240-247` |
| R2-16 | H | silent_pass | `butler/gateway/message_handler.py:912-913` |
| R2-17 | H | silent_pass | `butler/registry/skill_sources/marketplace.py:107-108, 250-256` |
| R2-18 | H | data_loss | `butler/skills/usage.py:24-30` |
| R2-19 | H | bad_fallback(12+ 状态文件统一反模式) | (跨文件) |

### R3 安全(3 条 = 0C + 3H)

| ID | Sev | 类型 | 文件 |
|----|-----|------|------|
| R3-1 | H | SSRF(TOCTOU) | `butler/tools/web_fetch.py:94 vs :102` |
| R3-2 | H | Untrusted-config → RCE chain | `butler/hooks/loader.py:86` + `butler/tools/path_safety.py:377-415` |
| R3-3 | H | Hooks 以 `bash -c` + 全 env 运行 | `butler/hooks/runner.py:522-531` |

### R4 并发(7 条 = 3C + 4H)

| ID | Sev | 类型 | 文件 |
|----|-----|------|------|
| R4-1 | C | missing_lock(cache LRU 多步非原子) | `butler/core/tool_result_cache.py:24, 80-100` |
| R4-2 | C | file_race(TOCTOU read-merge-write) | `butler/runtime/task_store.py:133-140` |
| R4-3 | C | missing_lock(gate 一致性) | `butler/human_gate.py:184-201, 313-354` |
| R4-4 | H | missing_lock(lock-released-too-early) | `butler/transport/provider_health.py:47-67, 81-92` |
| R4-5 | H | missing_lock(reference escape) | `butler/core/read_state.py:61-66, 86-113, 149-156` |
| R4-6 | H | file_race(TOCTOU read-merge-write) | `butler/core/session_todos.py:164-182` |
| R4-7 | H | async_misuse(跨 loop 共享) | `butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058, 1956` |

### R5 资源(10 条 = 4C + 6H)

| ID | Sev | 类型 | 文件 |
|----|-----|------|------|
| R5-1 | C | unbounded_cache | `butler/memory/prefetch_cache.py:13, 56-62` |
| R5-2 | C | db_leak(sqlite + ChromaDB) | `butler/orchestrator.py:169-176` |
| R5-3 | C | db_leak(tenant switch) | `butler/memory/facade.py:201-205` |
| R5-4 | C | unbounded_cache(dead code) | `butler/mcp/manager.py:48-49, 177` |
| R5-5 | H | subprocess_leak(pipe FD) | `butler/tools/terminal_impl.py:151-190` |
| R5-6 | H | unbounded_cache | `butler/tools/tool_audit.py:15, 104-108` |
| R5-7 | H | unbounded_cache | `butler/hooks/telemetry.py:15, 33` |
| R5-8 | H | unbounded_cache | `butler/core/read_state.py:18-19, 61-66` |
| R5-9 | H | retention_gap(实际 bounded, dead API) | `butler/gateway/inbound_idempotency.py:18-20, 165-171` |
| R5-10 | H | unbounded_cache | `butler/memory/observer_queue.py:20, 55-60` |

### R6 测试(4 条 = 1C + 3H)

| ID | Sev | 类型 | 文件 |
|----|-----|------|------|
| R6-1 | H | missing_tests | `butler/memory/corrective_recall.py`(90 LOC) |
| R6-2 | H | missing_tests | `butler/tools/tool_audit.py`(285 LOC) |
| R6-3 | H | missing_tests | `butler/gateway/platforms/wechat_format.py`(346 LOC) |
| R6-11 | C | failing_test | `tests/test_sprint23_tst10_6_magicmock_spec_policy.py::TestBaselineGate` |

### R7 文档(8 条 = 1C + 7H)

| ID | Sev | 类型 | 文件 |
|----|-----|------|------|
| R7-1 | C | config_drift(三处默认自相矛盾) | `BUTLER_ONBOARDING_WELCOME` |
| R7-2 | H | config_drift(5 个 env 错位) | 上下文压缩 5 env |
| R7-3 | H | config_drift | `BUTLER_PROVIDER_CIRCUIT_OPEN_SECONDS` |
| R7-4 | H | config_drift | 2 个 `BUTLER_TURN_BUDGET_*` |
| R7-5 | H | config_drift | 4 个 `BUTLER_TOOL_PRUNE_*` |
| R7-6 | H | config_drift | 2 个 `BUTLER_INSTRUCTION_WALKUP_MAX_*` |
| R7-7 | H | config_drift | `BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS` |
| R7-8 | H | config_drift | `BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH` |

### R8 配置(5 条 = 1C + 4H)

| ID | Sev | 类型 | 文件 |
|----|-----|------|------|
| R8-3 | C | dotenv_side_effect(import-time) | `butler/config.py:16, 22` |
| R8-5 | H | int_unsafe(12+ 处 `int(os.getenv(...))` 无 try/except) | 关键位置 |
| R8-6 | H | dead_config(6+ 文档化但代码 0 reader) | (跨文件) |
| R8-7 | H | undocumented_env(7+ env 代码读但文档/.env.example 完全未列) | (跨文件) |
| R8-8 | H | feature_flag_dark | `BUTLER_ENV=prod` |

---

## 9. 附录 B:Defer 列表(70 条 M/L)

不在本设计修复范围,完整列表见审计 doc。仅当 C/H 修复顺势覆盖时才一并处理。

- R1: R1-13/14/15/16/17/18/19/20(8 M)
- R2: R2-20/21/22/23(2 M + 2 已 M)
- R3: R3-4(1 L,prompt injection)
- R4: R4-8(1 M,lock 文档缺失)
- R5: R5-11(1 M)
- R6: R6-4/5/6/7/8(4 L,测试基础设施子项)
- R7: R7-9/10/11(1 M + 2 L)
- R8: R8-1/2/4/9/10(5 M;R8-1/2 已在 R7-4/7-8 涵盖)

---

## 10. 不在范围(Out of Scope)

1. 70 条 M/L 全部 defer(仅顺势覆盖)
2. 新功能、性能优化、防御性重构
3. 已被修复的 R6-11 baseline 失败在 PR-6 收口
4. 跨 PR 共享重构(若发现需 R1+R4 联合改的代码,改在 R1,R4 仅消费)
5. 任何 subagent 引入的新抽象(除非 C/H 修复必需)

---

**状态**:等用户审批 → 调用 `superpowers:writing-plans` skill 进入实现计划阶段。
